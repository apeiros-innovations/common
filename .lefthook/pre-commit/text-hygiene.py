#!/usr/bin/env python3

from __future__ import annotations

import re
import sys
from pathlib import Path

TRAILING_WHITESPACE = re.compile(rb"[\t\f\v ]+(?=\r?$)", re.MULTILINE)
FINAL_NEWLINES = re.compile(rb"(?:\r\n|\r|\n)+\Z")


def normalize(path: Path) -> None:
    if not path.is_file():
        return

    original = path.read_bytes()

    if not original:
        return

    if original.endswith(b"\r\n"):
        eol = b"\r\n"
    elif original.endswith(b"\r"):
        eol = b"\r"
    else:
        eol = b"\n"

    normalized = TRAILING_WHITESPACE.sub(b"", original)
    normalized = FINAL_NEWLINES.sub(b"", normalized)

    if normalized:
        normalized += eol

    if normalized != original:
        path.write_bytes(normalized)


for filename in sys.argv[1:]:
    normalize(Path(filename))
