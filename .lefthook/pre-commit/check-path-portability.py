#!/usr/bin/env python3

import os
import subprocess
import sys
import unicodedata

WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "CLOCK$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
    "COM¹",
    "COM²",
    "COM³",
    "LPT¹",
    "LPT²",
    "LPT³",
}

WINDOWS_INVALID = set('<>:"\\|?*')


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
        ]
    )

    return [os.fsdecode(path) for path in raw.split(b"\0") if path]


def portable_key(path: str) -> str:
    return unicodedata.normalize(
        "NFC",
        path,
    ).casefold()


def check_component(
    path: str,
    component: str,
) -> list[str]:
    problems: list[str] = []

    if component.endswith((" ", ".")):
        problems.append("path component ends with a space or period")

    invalid = sorted({char for char in component if char in WINDOWS_INVALID})

    if invalid:
        rendered = " ".join(repr(char) for char in invalid)

        problems.append(
            f"path component contains Windows-reserved character(s): {rendered}"
        )

    controls = sorted({ord(char) for char in component if ord(char) < 32})

    if controls:
        rendered = ", ".join(f"U+{code:04X}" for code in controls)

        problems.append(f"path component contains control character(s): {rendered}")

    stem = component.split(".", 1)[0].upper()

    if stem in WINDOWS_RESERVED:
        problems.append(f"path component uses Windows-reserved name {stem!r}")

    return [f"{path}: {problem}" for problem in problems]


seen: dict[str, str] = {}
failed = False

for path in tracked_paths():
    key = portable_key(path)
    previous = seen.get(key)

    if previous is not None and previous != path:
        print(
            f"{path}: path conflicts with {previous!r} "
            "on case-insensitive or Unicode-normalizing "
            "filesystems",
            file=sys.stderr,
        )

        failed = True
    else:
        seen[key] = path

    for component in path.split("/"):
        for problem in check_component(
            path,
            component,
        ):
            print(
                problem,
                file=sys.stderr,
            )
            failed = True

raise SystemExit(1 if failed else 0)
