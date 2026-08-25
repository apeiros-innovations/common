#!/usr/bin/env python3

import os
import subprocess
import sys

LIMIT_BYTES = 5 * 1024 * 1024
LIMIT_MIB = LIMIT_BYTES // (1024 * 1024)


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

added_paths = [os.fsdecode(path) for path in added_raw.split(b"\0") if path]

if not added_paths:
    raise SystemExit(0)

index_raw = git_output(
    "ls-files",
    "--cached",
    "-z",
    "--format=%(stage)%x09%(objecttype)%x09%(objectsize)%x09%(path)",
    "--",
    *added_paths,
)

failed = False

for record in index_raw.split(b"\0"):
    if not record:
        continue

    stage, object_type, object_size, path = record.split(b"\t", 3)

    if stage != b"0" or object_type != b"blob" or object_size == b"-":
        continue

    size = int(object_size)

    if size <= LIMIT_BYTES:
        continue

    filename = os.fsdecode(path)
    mib = size / (1024 * 1024)

    print(
        f"{filename}: staged blob is {mib:.2f} MiB; "
        f"repository limit is {LIMIT_MIB} MiB",
        file=sys.stderr,
    )

    failed = True

raise SystemExit(1 if failed else 0)
