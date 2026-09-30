"""Import paths for running the recipe's tests where it lives, in the SDK.

`ai.py` imports the starter's `src.capability`, exactly as it will inside
an app. Here that module is two directories over, so both go on the path.
Copied into an app, `ai.py` sits in `src/` and the app's own conftest
already makes `src` importable - this file stays behind.
"""
from __future__ import annotations

import sys
from pathlib import Path

RECIPE = Path(__file__).resolve().parents[1]
STARTER = RECIPE.parents[1] / "v2-starter"
TEMPLATES = RECIPE.parents[1]

for path in (RECIPE, STARTER, TEMPLATES):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
