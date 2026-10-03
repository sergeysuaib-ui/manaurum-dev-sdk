"""Documentation is part of the code, so it is part of the test suite.

Keep this file. It is the difference between "document as you write" being
a rule people mean and one they keep: an undocumented function fails here
in a second, instead of reaching production and costing the next person an
afternoon of reading the implementation to find out what a `None` meant.

The check is an `ast` walk - no imports, no I/O - so it costs nothing you
would notice. (After roiduani's 2.9.0 proposal, PR #18.)
"""
from __future__ import annotations

import ast
import pathlib

import pytest

#: Every module under src/, which is all of this app's own Python.
SRC = pathlib.Path(__file__).resolve().parent.parent / "src"
PY_FILES = sorted(SRC.rglob("*.py"))


def undocumented(tree: ast.AST) -> list[str]:
    """Every function or class in one module with no docstring.

    Private helpers count too: `_fail` is exactly the kind of function whose
    behaviour is non-obvious later, and a leading underscore is not an
    exemption from explaining yourself.

    Returns:
        ``"name (line N)"`` for each, by line; empty when the module is fully
        documented.
    """
    nodes = [node for node in ast.walk(tree)
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
             and not ast.get_docstring(node)]
    return [f"{node.name} (line {node.lineno})"
            for node in sorted(nodes, key=lambda node: node.lineno)]


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_every_module_has_a_docstring(path: pathlib.Path) -> None:
    """Each module says what it is for and why it is its own file.

    An empty package marker (`__init__.py` with nothing in it) is exempt.
    """
    # Bytes, not text: ast honours a BOM and a coding line the way Python
    # does, and PowerShell 5.1 writes UTF-8 with a BOM.
    tree = ast.parse(path.read_bytes())
    if path.name == "__init__.py" and not tree.body:
        return
    assert ast.get_docstring(tree), (
        f"{path.name} has no module docstring - say what this file is for "
        f"and why it is its own file")


@pytest.mark.parametrize("path", PY_FILES, ids=lambda p: p.name)
def test_every_function_and_class_is_documented(path: pathlib.Path) -> None:
    """No function or class ships without a docstring."""
    missing = undocumented(ast.parse(path.read_bytes()))
    assert not missing, (
        f"{path.name}: undocumented - {', '.join(missing)}. One summary line is "
        f"enough when there is nothing non-obvious to say; write it now rather "
        f"than after the app works.")
