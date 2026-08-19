#!/usr/bin/env python3

import os
import subprocess
import sys


def git_output(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
    )


paths = sys.argv[1:]

if not paths:
    raise SystemExit(0)

added_raw = git_output(
    "diff",
    "--cached",
    "--name-only",
    "--diff-filter=A",
    "-z",
    "--",
    *paths,
)

added = [
    path
    for path in added_raw.split(b"\0")
    if path
]

if not added:
    raise SystemExit(0)

tracked_raw = git_output(
    "ls-files",
    "-z",
)

tracked_gitignores = {
    os.fsdecode(path)
    for path in tracked_raw.split(b"\0")
    if (
        path
        and os.path.basename(
            os.fsdecode(path)
        )
        == ".gitignore"
    )
}

if not tracked_gitignores:
    raise SystemExit(0)

result = subprocess.run(
    [
        "git",
        "check-ignore",
        "--no-index",
        "-v",
        "-z",
        "--stdin",
    ],
    input=b"\0".join(added) + b"\0",
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    check=False,
)

if result.returncode not in {
    0,
    1,
}:
    raise SystemExit(
        result.returncode
    )

fields = result.stdout.split(b"\0")

if fields and fields[-1] == b"":
    fields.pop()

if len(fields) % 4 != 0:
    print(
        "git check-ignore returned malformed "
        "verbose output",
        file=sys.stderr,
    )
    raise SystemExit(1)

failed = False

for index in range(
    0,
    len(fields),
    4,
):
    (
        source_raw,
        line_raw,
        pattern_raw,
        path_raw,
    ) = fields[index : index + 4]

    source = os.fsdecode(
        source_raw
    )

    if source not in tracked_gitignores:
        continue

    path = os.fsdecode(
        path_raw
    )
    pattern = os.fsdecode(
        pattern_raw
    )
    line = line_raw.decode(
        "ascii",
        errors="replace",
    )

    print(
        f"{path}: force-added despite tracked "
        f"ignore rule {source}:{line}: {pattern}",
        file=sys.stderr,
    )

    failed = True

raise SystemExit(1 if failed else 0)
