#!/usr/bin/env python3

import runpy
from pathlib import Path

script = (
    Path(__file__).resolve().parent
    / ".."
    / "lib"
    / "dependency-security.py"
)

runpy.run_path(
    str(script),
    run_name="__main__",
)
