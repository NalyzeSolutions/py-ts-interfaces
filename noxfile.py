from functools import wraps
from typing import Any, Callable, TypeVar, cast

from nox_poetry import Session
from nox_poetry import session as nox_session

SUPPORTED_PYTHON_VERSIONS = ["3.8", "3.9", "3.10", "3.11"]

F = TypeVar("F", bound=Callable[..., Any])


def install_poetry_deps(fn: F) -> F:
    @wraps(fn)
    def wrapper(session: Session, *args, **kwargs):
        session.install("-r", str(session.poetry.export_requirements()))
        return fn(session, *args, **kwargs)

    return cast(F, wrapper)


@nox_session(python=SUPPORTED_PYTHON_VERSIONS)
@install_poetry_deps
def code_quality(session: Session) -> None:
    session.run("black", "--check", "py_ts_interfaces")
    session.run("flake8", "--count", "py_ts_interfaces")
    session.run("isort", "-c", "py_ts_interfaces")


@nox_session(python=SUPPORTED_PYTHON_VERSIONS)
@install_poetry_deps
def type_check(session: Session) -> None:
    session.run("mypy", "py_ts_interfaces")


@nox_session(python=SUPPORTED_PYTHON_VERSIONS)
@install_poetry_deps
def pytests(session: Session) -> None:
    session.run("python", "-m", "pytest")
