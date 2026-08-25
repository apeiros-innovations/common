#!/usr/bin/env python3

import os
import posixpath
import re
import subprocess
import sys

WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def git_output(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
    )


def escapes_repository(
    path: str,
    target: str,
) -> bool:
    portable_target = target.replace(
        "\\",
        "/",
    )

    if portable_target.startswith("/") or WINDOWS_DRIVE.match(target):
        return True

    resolved = posixpath.normpath(
        posixpath.join(
            posixpath.dirname(path),
            portable_target,
        )
    )

    return resolved == ".." or resolved.startswith("../")


paths = sys.argv[1:]

if not paths:
    raise SystemExit(0)

raw = git_output(
    "ls-files",
    "--cached",
    "-z",
    "--format=%(stage)%x09%(objectmode)%x09%(objectname)%x09%(path)",
    "--",
    *paths,
)

failed = False

for record in raw.split(b"\0"):
    if not record:
        continue

    stage, mode, oid, path_raw = record.split(
        b"\t",
        3,
    )

    if stage != b"0" or mode != b"120000":
        continue

    path = os.fsdecode(path_raw)

    target_raw = git_output(
        "cat-file",
        "blob",
        oid.decode("ascii"),
    )
    target = os.fsdecode(target_raw)

    if not target:
        print(
            f"{path}: symlink target is empty",
            file=sys.stderr,
        )
        failed = True
        continue

    if escapes_repository(
        path,
        target,
    ):
        print(
            f"{path}: symlink target {target!r} resolves outside the repository",
            file=sys.stderr,
        )
        failed = True

raise SystemExit(1 if failed else 0)
