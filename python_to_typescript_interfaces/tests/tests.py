from copy import deepcopy
from itertools import count
from typing import Any
from unittest.mock import ANY, patch

import pytest
from astroid import AnnAssign, ClassDef, extract_node

from python_to_typescript_interfaces import Interface, Parser
from python_to_typescript_interfaces.parser import (
    PossibleInterfaceReference,
    PossibleInterfaceReferences,
    PreparedInterfaces,
)
from python_to_typescript_interfaces.tests import utils


@pytest.fixture(scope="module")
def interface_qualname() -> str:
    return f"{Interface.__module__}.{Interface.__qualname__}"


PYTHON_VERSION = utils.get_version()


TEST_ONE = """
    class Foo:
        pass
"""
TEST_TWO = """
    from python_to_typescript_interfaces import Interface

    class Foo(Interface):
        pass
"""
TEST_THREE = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Foo(Interface):
        pass
"""
TEST_FOUR = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Foo(Interface):
        pass

    @dataclass
    class Bar(Interface):
        pass

    class Baz(Interface):
        pass

    class Parent:
        class Child1(Interface):
            pass

        @dataclass
        class Child2(Interface):
            pass
"""
TEST_FIVE = """
    from dataclasses import dataclass

    class Interface:
        pass

    class Foo(Interface):
        pass

    @dataclass
    class Bar(Interface):
        pass
"""

TEST_SIX = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Foo(Interface):  #@
        aaa: str
        bbb: int
        ccc: bool
        ddd = 100

        def foo(self) -> None:
            pass
"""
TEST_SEVEN = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Bar(Interface):  #@
        def foo(self) -> None:
            pass

        aaa: str = 'hello'
        bbb: int = 5
        ccc: bool = True
"""

TEST_EIGHT = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Foo(Interface):
        aaa: str

    @dataclass
    class Foo(Interface):
        bbb: int
"""

TEST_NINE = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class Foo(Interface):
        aaa: str

    @dataclass
    class Bar(Interface):
        bbb: int
        foo: Foo
"""

TEST_TEN = """
    from dataclasses import dataclass
    from python_to_typescript_interfaces import Interface

    @dataclass
    class One(Interface):
        aaa: str

    @dataclass
    class Two(Interface):
        bbb: int
        one: One

    @dataclass
    class Three(Interface):
        bbb: int
        two: Two

    @dataclass
    class All(Interface):
        bbb: int
        one: One
        two: Two
        three: Three
"""

TEST_ENUM = """
    from dataclasses import dataclass
    from enum import Enum

    from python_to_typescript_interfaces import Interface

    @dataclass
    class Animal(Interface, Enum):
        DOG = "dog"
        CAT = "cat"
"""


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize(
    "code, expected_call_count, expected_prepared",
    [
        (TEST_ONE, 0, {}),
        (TEST_TWO, 0, {}),
        (TEST_THREE, 1, {"Foo": ANY}),
        (TEST_FOUR, 3, {"Foo": ANY, "Bar": ANY, "Child2": ANY}),
        (TEST_FIVE, 0, {}),
        (TEST_EIGHT, 1, {"Foo": ANY}),
        (TEST_NINE, 2, {"Foo": ANY, "Bar": ANY}),
        (TEST_TEN, 4, {"One": ANY, "Two": ANY, "Three": ANY, "All": ANY}),
    ],
)
def test_parser_parse(
    code: str, expected_call_count: int, expected_prepared: Any, interface_qualname: str
) -> None:
    parser = Parser(interface_qualname)
    with patch.object(Parser, "get_types_from_classdef") as mock_writer:
        parser.parse(code=code)
        assert mock_writer.call_count == expected_call_count
        assert parser.prepared == expected_prepared


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize(
    "code, expected_call_count, expected_prepared",
    [
        (TEST_ENUM, 0, {"enum Animal": {"CAT": "cat", "DOG": "dog"}}),
    ],
)
def test_parser_parse_enum(
    code: str, expected_call_count: int, expected_prepared: Any, interface_qualname: str
) -> None:
    parser = Parser(interface_qualname)
    with patch.object(Parser, "get_types_from_classdef") as mock_writer:
        parser.parse(code=code)
        assert mock_writer.call_count == expected_call_count
        assert parser.prepared == expected_prepared


@pytest.mark.parametrize(
    "prepared_mocks, expected",
    [
        ({"abc": {"def": "ghi"}}, """export interface abc {\n    def: ghi;\n}\n"""),
        (
            {"abc": {"def": "ghi", "jkl": "mno"}},
            """export interface abc {\n    def: ghi;\n    jkl: mno;\n}\n""",
        ),
        ({"abc": {}}, """export interface abc {\n}\n"""),
        (
            {"abc": {"def": PossibleInterfaceReference("ghi")}, "ghi": {"jkl": "mno"}},
            """export interface abc {\n    def: ghi;\n}\n\n"""
            """export interface ghi {\n    jkl: mno;\n}\n""",
        ),
        (
            {"enum Animal": {"CAT": "cat", "DOG": "dog"}},
            """export enum Animal {\n    CAT = "cat",\n    DOG = "dog",\n}\n""",
        ),
        (
            {
                "abc": {"def": PossibleInterfaceReference("ghi")},
                "ghi": {"jkl": "mno"},
                "enum pqr": {"stu": "vwx"},
            },
            """export interface abc {\n    def: ghi;\n}\n\n"""
            """export interface ghi {\n    jkl: mno;\n}\n\n"""
            """export enum pqr {\n    stu = "vwx",\n}\n""",
        ),
    ],
)
def test_parser_flush_with_export(
    prepared_mocks: Any, expected: str, interface_qualname: str
) -> None:
    """
    When the parser flushes its prepared interfaces, it should generate
    valid TS interfaces.
    """
    parser = Parser(interface_qualname)
    parser.prepared = prepared_mocks
    assert parser.flush(True) == expected


@pytest.mark.parametrize(
    "prepared_mocks, expected",
    [
        ({"abc": {"def": "ghi"}}, """interface abc {\n    def: ghi;\n}\n"""),
        (
            {"abc": {"def": "ghi", "jkl": "mno"}},
            """interface abc {\n    def: ghi;\n    jkl: mno;\n}\n""",
        ),
        ({"abc": {}}, """interface abc {\n}\n"""),
        (
            {"abc": {"def": PossibleInterfaceReference("ghi")}, "ghi": {"jkl": "mno"}},
            """interface abc {\n    def: ghi;\n}\n\n"""
            """interface ghi {\n    jkl: mno;\n}\n""",
        ),
        (
            {"enum Animal": {"CAT": "cat", "DOG": "dog"}},
            """enum Animal {\n    CAT = "cat",\n    DOG = "dog",\n}\n""",
        ),
        (
            {
                "abc": {"def": PossibleInterfaceReference("ghi")},
                "ghi": {"jkl": "mno"},
                "enum pqr": {"stu": "vwx"},
            },
            """interface abc {\n    def: ghi;\n}\n\n"""
            """interface ghi {\n    jkl: mno;\n}\n\n"""
            """enum pqr {\n    stu = "vwx",\n}\n""",
        ),
    ],
)
def test_parser_flush_without_export(
    prepared_mocks: Any, expected: str, interface_qualname: str
) -> None:
    """
    When the parser flushes its prepared interfaces, it should generate
    valid TS interfaces.
    """
    parser = Parser(interface_qualname)
    parser.prepared = prepared_mocks
    assert parser.flush(False) == expected


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize(
    "code, expected, expected_possible_interface_references",
    [
        ("baz: str", ("baz", "string"), {}),
        ("ace: int", ("ace", "number"), {}),
        ("ace: float", ("ace", "number"), {}),
        ("ace: complex", ("ace", "number"), {}),
        ("ace: bool", ("ace", "boolean"), {}),
        ("ace: Any", ("ace", "any"), {}),
        ("foo: List", ("foo", "Array<any>"), {}),
        ("foo: list", ("foo", "Array<any>"), {}),
        ("foo: Dict", ("foo", "Record<any, any>"), {}),
        ("foo: dict", ("foo", "Record<any, any>"), {}),
        ("bar: Tuple", ("bar", "[any]"), {}),
        ("bar: tuple", ("bar", "[any]"), {}),
        ("foo: List[str]", ("foo", "Array<string>"), {}),
        ("foo: list[str]", ("foo", "Array<string>"), {}),
        ("bar: Tuple[str, int]", ("bar", "[string, number]"), {}),
        ("bar: tuple[str, int]", ("bar", "[string, number]"), {}),
        ("baz: Optional[str]", ("baz", "string | null"), {}),
        ("ace: Optional[int]", ("ace", "number | null"), {}),
        ("ace: Optional[float]", ("ace", "number | null"), {}),
        ("ace: Optional[complex]", ("ace", "number | null"), {}),
        ("ace: Optional[bool]", ("ace", "boolean | null"), {}),
        ("ace: Optional[Any]", ("ace", "any | null"), {}),
        ("foo: Dict[str, int]", ("foo", "Record<string, number>"), {}),
        ("foo: dict[str, int]", ("foo", "Record<string, number>"), {}),
        ("foo: Dict[int, int]", ("foo", "Record<number, number>"), {}),
        ("foo: dict[int, int]", ("foo", "Record<number, number>"), {}),
        ("bar: Optional[Tuple[str, int]]", ("bar", "[string, number] | null"), {}),
        ("bar: Optional[tuple[str, int]]", ("bar", "[string, number] | null"), {}),
        (
            "bar: Tuple[List[Optional[Tuple[str, int]]], str, int]",
            ("bar", "[Array<[string, number] | null>, string, number]"),
            {},
        ),
        (
            "bar: tuple[list[Optional[tuple[str, int]]], str, int]",
            ("bar", "[Array<[string, number] | null>, string, number]"),
            {},
        ),
        ("lol: Union[str, int, float]", ("lol", "string | number"), {}),
        ("lol: Union", ("lol", "any"), {}),
        (
            "whatever: 'StringForward'",
            ("whatever", PossibleInterfaceReference("StringForward")),
            {"StringForward": ["parent_name"]},
        ),
        (
            "whatever: List[StringForward]",
            ("whatever", PossibleInterfaceReference("Array<StringForward>")),
            {"StringForward": ["parent_name"]},
        ),
        (
            "whatever: List[Union[StringForward, bool]]",
            (
                "whatever",
                PossibleInterfaceReference("Array<StringForward | boolean>"),
            ),
            {"StringForward": ["parent_name"]},
        ),
        (
            "whatever: NakedReference",
            ("whatever", PossibleInterfaceReference("NakedReference")),
            {"NakedReference": ["parent_name"]},
        ),
        (
            "whatever: Union[NakedReference, StringForward]",
            ("whatever", PossibleInterfaceReference("NakedReference | StringForward")),
            {"NakedReference": ["parent_name"], "StringForward": ["parent_name"]},
        ),
        ("whatever: 1234", ("whatever", "UNKNOWN"), {}),
    ],
)
def test_parse_annassign_node(
    code: str, expected: Any, expected_possible_interface_references: Any
) -> None:
    parser = Parser(interface_qualname)
    ann_assign = extract_node(code)
    assert isinstance(ann_assign, AnnAssign)
    assert parser.parse_annassign_node(ann_assign, "parent_name") == expected
    assert (
        parser.possible_interface_references == expected_possible_interface_references
    )


@pytest.mark.filterwarnings("ignore::UserWarning")
def test_parse_annassign_node_sequence() -> None:
    parser = Parser(interface_qualname)
    ann_assign_0 = extract_node("whatever: Union[NakedReference, StringForward]")
    isinstance(ann_assign_0, AnnAssign)
    ann_assign_1 = extract_node("other: StringForward")
    isinstance(ann_assign_1, AnnAssign)
    ann_assign_2 = extract_node("another: List[NakedReference]")
    isinstance(ann_assign_2, AnnAssign)
    ann_assign_3 = extract_node("another_again: Optional[NakedReference]")
    isinstance(ann_assign_3, AnnAssign)
    parser.parse_annassign_node(ann_assign_0, "parent_name_0")
    parser.parse_annassign_node(ann_assign_1, "parent_name_1")
    parser.parse_annassign_node(ann_assign_2, "parent_name_2")
    # NakedReference is referenced twice in parent_name_2
    # but is stored also once in the possible_interface_references["NakedReference"]
    parser.parse_annassign_node(ann_assign_3, "parent_name_2")
    assert parser.possible_interface_references == {
        "NakedReference": ["parent_name_0", "parent_name_2"],
        "StringForward": ["parent_name_0", "parent_name_1"],
    }


@pytest.mark.parametrize(
    "code, expected_call_count, expected_node_name",
    [(TEST_SIX, 0, "Foo"), (TEST_SEVEN, 0, "Bar")],
)
def test_get_types_from_classdef(
    code: str, expected_call_count: int, expected_node_name
) -> None:
    parser = Parser(interface_qualname)
    class_def = extract_node(code)
    assert isinstance(class_def, ClassDef)
    with patch.object(Parser, "parse_annassign_node") as annassign_parser:
        k, v = count(0, 2), count(1, 2)
        annassign_parser.side_effect = lambda node, parent_name: (
            str(next(k)),
            str(next(v)),
        )

        result = parser.get_types_from_classdef(class_def)
        assert result == {"0": "1", "2": "3", "4": "5"}
        assert annassign_parser.call_count == 3
        assert annassign_parser.call_args.args == (ANY, expected_node_name)


@pytest.mark.parametrize(
    "interfaces, possible_interface_references",
    [
        ({"interfaceA": {"name": "str"}, "interfaceB": {"another_name": "int"}}, {}),
        (
            {
                "interfaceA": {"name": PossibleInterfaceReference("interfaceB")},
                "enum TestEnum": {"another_name": "int"},
                "interfaceB": {"another_name": "TestEnum"},
            },
            {"interfaceB": ["interfaceA"]},
        ),
        (
            {"interfaceA": {"name": PossibleInterfaceReference("interfaceA")}},
            {"interfaceA": ["interfaceA"]},
        ),
    ],
)
def test_ensure_possible_interface_references_valid__succeeds(
    interfaces: PreparedInterfaces,
    possible_interface_references: PossibleInterfaceReferences,
) -> None:
    parser = Parser(interface_qualname)
    parser.prepared = interfaces
    parser.possible_interface_references = possible_interface_references
    copied_interfaces = deepcopy(interfaces)
    parser.ensure_possible_interface_references_valid()
    assert copied_interfaces == parser.prepared  # Make sure no mutations occurred


@pytest.mark.parametrize(
    "interfaces, possible_interface_references",
    [
        (
            {
                "interfaceA": {"name": PossibleInterfaceReference("interfaceB")},
                "interfaceB": {
                    "another_name": PossibleInterfaceReference("interfaceC")
                },
            },
            {"interfaceB": ["interfaceA"], "interfaceC": ["interfaceB"]},
        ),
        (
            {"interfaceA": {"name": PossibleInterfaceReference("interfaceB")}},
            {"interfaceB": ["interfaceA"]},
        ),
    ],
)
def test_ensure_possible_interface_references_valid__fails(
    interfaces: PreparedInterfaces,
    possible_interface_references: PossibleInterfaceReferences,
) -> None:
    with pytest.raises(RuntimeError):
        parser = Parser(interface_qualname)
        parser.prepared = interfaces
        parser.possible_interface_references = possible_interface_references
        parser.ensure_possible_interface_references_valid()


TEST_INHERITANCE_ONE = """
    from dataclasses import dataclass
    from enum import Enum

    from python_to_typescript_interfaces import Interface

    @dataclass
    class Simple0(Interface):
        a: int
        b: str

    @dataclass
    class Simple1(Simple0, Interface):
        c: int
"""

TEST_INHERITANCE_TWO = """
    from dataclasses import dataclass
    from enum import Enum

    from python_to_typescript_interfaces import Interface

    @dataclass
    class Class0(Interface):
        a: int
        b: str

    @dataclass
    class Class1(Interface):
        c: int

    @dataclass
    class Class2(AnotherClass, Class0, Class1, Interface):
        d: str
"""


@pytest.mark.filterwarnings("ignore::UserWarning")
@pytest.mark.parametrize(
    "code, expected_prepared, expected_interface_inheritances, expected_result",
    [
        (
            TEST_INHERITANCE_ONE,
            {
                "Simple0": {"a": "number", "b": "string"},
                "Simple1": {"c": "number"},
            },
            {"Simple1": ["Simple0"]},
            """export interface Simple0 {\n    a: number;\n    b: string;\n}\n\n"""
            """export interface Simple1 extends Simple0 {\n    c: number;\n}\n""",
        ),
        (
            TEST_INHERITANCE_TWO,
            {
                "Class0": {"a": "number", "b": "string"},
                "Class1": {"c": "number"},
                "Class2": {"d": "string"},
            },
            {"Class2": ["AnotherClass", "Class0", "Class1"]},
            """export interface Class0 {\n    a: number;\n    b: string;\n}\n\n"""
            """export interface Class1 {\n    c: number;\n}\n\n"""
            """export interface Class2 extends Class0, Class1 {\n    d: string;\n}\n""",
        ),
    ],
)
def test_parser_parse_interface_with_inheritance(
    code: str,
    expected_prepared: Any,
    expected_interface_inheritances: Any,
    expected_result: str,
    interface_qualname: str,
) -> None:
    parser = Parser(interface_qualname)
    parser.parse(code=code)

    assert parser.prepared == expected_prepared
    assert parser.interface_inheritances == expected_interface_inheritances
    assert parser.flush(True) == expected_result
