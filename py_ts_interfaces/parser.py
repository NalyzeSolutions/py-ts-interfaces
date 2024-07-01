import warnings
from collections import deque
from typing import Dict, List, NamedTuple, Optional, Tuple, Union

import astroid


class Interface:
    pass


class PossibleInterfaceReference(str):
    pass


TYPE_MAP: Dict[str, str] = {
    "bool": "boolean",
    "str": "string",
    "int": "number",
    "float": "number",
    "complex": "number",
    "Any": "any",
    "Dict": "Record<any, any>",
    "List": "Array<any>",
    "Tuple": "[any]",
    "dict": "Record<any, any>",
    "list": "Array<any>",
    "tuple": "[any]",
    "Union": "any",
}

SUBSCRIPT_FORMAT_MAP: Dict[str, str] = {
    "Dict": "Record<%s>",
    "List": "Array<%s>",
    "Optional": "%s | null",
    "Tuple": "[%s]",
    "Union": "%s",
    "dict": "Record<%s>",
    "list": "Array<%s>",
    "tuple": "[%s]",
}


InterfaceAttributes = Dict[str, str]
PreparedInterfaces = Dict[str, InterfaceAttributes]
PossibleInterfaceReferences = Dict[str, List[str]]


class ParsedAnnAssign(NamedTuple):
    attr_name: str
    attr_type: str


class Parser:
    def __init__(self, interface_qualname: str) -> None:
        self.interface_qualname = interface_qualname
        self.prepared: PreparedInterfaces = {}
        self.possible_interface_references: PossibleInterfaceReferences = {}
        self.interface_inheritances: PossibleInterfaceReferences = {}

    def parse(self, code: str) -> None:
        queue = deque([astroid.parse(code)])
        while queue:
            current = queue.popleft()
            children = current.get_children()
            if not isinstance(current, astroid.ClassDef):
                queue.extend(children)
                continue

            if not current.is_subtype_of(self.interface_qualname):
                queue.extend(children)
                continue

            if not has_dataclass_decorator(current.decorators):
                warnings.warn(
                    "Non-dataclasses are not supported, see documentation.", UserWarning
                )
                continue

            if current.name in self.prepared:
                warnings.warn(
                    f"Found duplicate interface with name {current.name}."
                    "All interfaces after the first will be ignored",
                    UserWarning,
                )
                continue

            not_interface_current_base_names = [
                base.name for base in current.bases if base.name != "Interface"
            ]
            enum_in_current_bases = (
                len([base for base in current.bases if base.name == "Enum"]) > 0
            )
            if len(not_interface_current_base_names) > 0 and not enum_in_current_bases:
                self.interface_inheritances[current.name] = (
                    not_interface_current_base_names
                )

            if enum_in_current_bases:
                # Handle enum types
                self.prepared[f"enum {current.name}"] = {}
                for child in current.body:
                    if isinstance(child, astroid.Assign):
                        self.prepared[f"enum {current.name}"][
                            child.targets[0].name
                        ] = child.value.value
            else:
                self.prepared[current.name] = self.get_types_from_classdef(current)

    def flush(self, should_export: bool) -> str:
        serialized: List[str] = []
        interface_names = set(self.prepared.keys())

        for interface, attributes in self.prepared.items():
            s = "export " if should_export else ""
            if interface.startswith("enum"):
                s += f"{interface} {{\n"
                for attribute_name, attribute_type in attributes.items():
                    s += f'    {attribute_name} = "{attribute_type}",\n'
                s += "}"
            else:
                extends = " "
                if interface in self.interface_inheritances:
                    # We keep only inheritances for which we have the interface
                    filtered_interface_inheritances = [
                        item
                        for item in self.interface_inheritances[interface]
                        if item in interface_names
                    ]
                    if len(filtered_interface_inheritances) > 0:
                        extends = (
                            f" extends {', '.join(filtered_interface_inheritances)} "
                        )
                s += f"interface {interface}{extends}{{\n"
                for attribute_name, attribute_type in attributes.items():
                    s += f"    {attribute_name}: {attribute_type};\n"
                s += "}"
            serialized.append(s)

        self.prepared.clear()
        return "\n\n".join(serialized).strip() + "\n"

    def get_types_from_classdef(self, node: astroid.ClassDef) -> Dict[str, str]:
        serialized_types: Dict[str, str] = {}
        for child in node.body:
            if not isinstance(child, astroid.AnnAssign):
                continue
            child_name, child_type = self.parse_annassign_node(child, node.name)

            serialized_types[child_name] = child_type
        return serialized_types

    def parse_annassign_node(
        self, node: astroid.AnnAssign, parent_name: str
    ) -> ParsedAnnAssign:
        def helper(
            node: astroid.node_classes.NodeNG,
        ) -> Tuple[Union[str, PossibleInterfaceReference], List[str]]:
            type_value = "UNKNOWN"
            possible_interface_references: List[str] = []
            if isinstance(node, astroid.Name):
                # When the node is of an astroid.Name type, it could have a
                # name that exists in our TYPE_MAP, it could have a name that
                # refers to another class previously defined in the source, or
                # it could be a forward reference to a class that has yet to
                # be parsed.
                # We will have to assume it is a valid forward reference now and
                # then just double check that it does indeed reference another
                # Interface class as a post-parse step.
                type_value = TYPE_MAP.get(
                    node.name, PossibleInterfaceReference(node.name)
                )
                if node.name == "Union":
                    warnings.warn(
                        "Came across an annotation for Union without any indexed types!"
                        " Coercing the annotation to any.",
                        UserWarning,
                    )

            elif isinstance(node, astroid.Const) and node.name == "str":
                # When the node is of an astroid.Const type, it could be one of
                # num, str, bool, None, or bytes.
                # If it is Const.str, then it is possible that the value is a
                # reference to a class previously defined in the source or it could
                # be a forward reference to a class that has yet to be parsed.
                type_value = PossibleInterfaceReference(node.value)

            elif isinstance(node, astroid.Subscript):
                subscript_value = node.value
                type_format = SUBSCRIPT_FORMAT_MAP[subscript_value.name]
                subscript_type, subscript_possible_interface_references = helper(
                    node.slice
                )
                possible_interface_references.extend(
                    subscript_possible_interface_references
                )
                type_value = type_format % subscript_type

            elif isinstance(node, astroid.Tuple):
                (
                    inner_types,
                    inner_possible_interface_references,
                ) = get_inner_tuple_types(node)
                possible_interface_references.extend(
                    inner_possible_interface_references
                )
                delimiter = get_inner_tuple_delimiter(node)
                if delimiter == " | ":
                    inner_types_deduplicated = []

                    # Deduplicate inner types using a list to preserve order
                    for inner_type in inner_types:
                        if inner_type not in inner_types_deduplicated:
                            inner_types_deduplicated.append(inner_type)

                    inner_types = inner_types_deduplicated

                if delimiter != "UNKNOWN":
                    type_value = delimiter.join(inner_types)

            if isinstance(type_value, PossibleInterfaceReference):
                possible_interface_references.append(type_value)

            return type_value, possible_interface_references

        def get_inner_tuple_types(
            tuple_node: astroid.Tuple,
        ) -> Tuple[List[str], List[str]]:
            # avoid using Set to keep order. We also want repetitions
            # to avoid problems with tuples where repeated types do have
            # a meaning (e.g., Dict[int, int]).
            inner_types: List[str] = []
            inner_possible_interface_references: List[str] = []
            for child in tuple_node.get_children():
                child_attr_type, child_possible_interface_references = helper(child)
                inner_possible_interface_references.extend(
                    child_possible_interface_references
                )
                inner_types.append(child_attr_type)

            return inner_types, inner_possible_interface_references

        def get_inner_tuple_delimiter(tuple_node: astroid.Tuple) -> str:
            parent_subscript_name = tuple_node.parent.value.name
            delimiter = "UNKNOWN"
            if parent_subscript_name in {"Dict", "Tuple", "dict", "tuple"}:
                delimiter = ", "
            elif parent_subscript_name == "Union":
                delimiter = " | "
            return delimiter

        attr_type, possible_interface_references = helper(node.annotation)
        if len(possible_interface_references) > 0:
            for possible_interface_reference in possible_interface_references:
                if (
                    possible_interface_reference in self.possible_interface_references
                    and parent_name
                    not in self.possible_interface_references[
                        possible_interface_reference
                    ]
                ):
                    # We append the list only if :
                    # - the list for this possible_interface_reference already exists
                    # - the parent_name is not already in the list
                    self.possible_interface_references[
                        possible_interface_reference
                    ].append(parent_name)
                elif (
                    possible_interface_reference
                    not in self.possible_interface_references
                ):
                    # If the list for this possible_interface_reference doesn't exists,
                    # we create it and add the first parent_name
                    self.possible_interface_references[possible_interface_reference] = [
                        parent_name
                    ]

        return ParsedAnnAssign(node.target.name, attr_type)

    def ensure_possible_interface_references_valid(self) -> None:
        interface_names = set(self.prepared.keys())
        # In the case of enums, interface name is prefixed with "enum"
        # to know how to transform it in TS correctly,
        # so we need to remove this prefix
        interface_names_without_prefix = [
            interface_name.replace("enum ", "") for interface_name in interface_names
        ]
        for (
            possible_interface_reference,
            interfaces_that_use_this_reference,
        ) in self.possible_interface_references.items():
            if possible_interface_reference not in interface_names_without_prefix:

                raise RuntimeError(
                    f"Invalid nested Interface reference "
                    f"'{possible_interface_reference}' found in interface"
                    f"{'s' if len(interfaces_that_use_this_reference) > 1 else ''}"
                    f" {', '.join(interfaces_that_use_this_reference)}!\n"
                    f"Does '{possible_interface_reference}' exist "
                    f"and is it an Interface?"
                )


def has_dataclass_decorator(decorators: Optional[astroid.Decorators]) -> bool:
    if not decorators:
        return False

    return any(
        (
            (getattr(decorator.func, "name", None) == "dataclass")
            if isinstance(decorator, astroid.Call)
            else decorator.name == "dataclass"
        )
        for decorator in decorators.nodes
    )
