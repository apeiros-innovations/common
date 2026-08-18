#!/usr/bin/env python3

from __future__ import annotations

import subprocess
import sys
import unicodedata

raw = subprocess.check_output(["git", "ls-files", "-z"])
paths = [
    path.decode("utf-8", errors="surrogateescape")
    for path in raw.split(b"\0")
    if path
]

seen: dict[str, str] = {}
failed = False

for path in paths:
    key = unicodedata.normalize("NFC", path).casefold()
    previous = seen.get(key)

    if previous is not None and previous != path:
        print(
            f"case-insensitive path conflict: {previous!r} <-> {path!r}",
            file=sys.stderr,
        )
        failed = True
    else:
        seen[key] = path

raise SystemExit(1 if failed else 0)
