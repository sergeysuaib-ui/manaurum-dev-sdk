"""Documentation is part of the code, so it is part of the test suite.

Keep this file. It is the difference between "document as you write" being
a rule people mean and one they keep: an undocumented function fails here
in a second, instead of reaching production and costing the next person an
afternoon of reading the implementation to find out what a `None` meant.

The check is deliberately cheap — an `ast` walk, no imports, no I/O — so it
adds nothing you would notice to the run.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

#: Every module under src/, which is all of this app's own Python.
SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
PY_FILES = sorted(p for p in SRC.rglob("*.py") if p.name != "__init__.py")


def undocumented(tree: ast.AST) -> list[str]:
    """Find every definition in one module with no docstring.

    Args:
        tree: A parsed module.

    Returns:
        ``"name (line N)"`` for each offender, in source order. Empty
        means the module is fully documented.

        Private helpers are INCLUDED on purpose: `_gateway` and `_fail`
        are exactly the functions whose behaviour is non-obvious later,
        and the leading underscore is not an exemption from explaining
        yourself.
    """
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not ast.get_docstring(node):
                out.append(f"{node.name} (line {node.lineno})")
    return out


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_every_module_has_a_docstring(path: pathlib.Path) -> None:
    """Each module says what it is for and why it exists separately.

    Args:
        path: One module under src/.
    """
    tree = ast.parse(path.read_text())
    assert ast.get_docstring(tree), (
        f"{path.name} has no module docstring — say what this file is for "
        f"and why it is its own file"
    )


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_every_function_and_class_is_documented(path: pathlib.Path) -> None:
    """No function or class ships without a docstring.

    Args:
        path: One module under src/.
    """
    missing = undocumented(ast.parse(path.read_text()))
    assert not missing, (
        f"{path.name}: undocumented — {', '.join(missing)}. "
        f"One summary line is enough when there is nothing non-obvious to "
        f"say; write it now rather than after the app works."
    )
