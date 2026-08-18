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

    data = path.read_bytes()
    if not data:
        return

    if data.endswith(b"\r\n"):
        eol = b"\r\n"
    elif data.endswith(b"\r"):
        eol = b"\r"
    else:
        eol = b"\n"

    data = TRAILING_WHITESPACE.sub(b"", data)
    data = FINAL_NEWLINES.sub(b"", data)

    if data:
        data += eol

    path.write_bytes(data)


for filename in sys.argv[1:]:
    normalize(Path(filename))
