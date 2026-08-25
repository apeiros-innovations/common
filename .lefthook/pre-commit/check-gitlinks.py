#!/usr/bin/env python3

import os
import subprocess
import sys


def git_run(
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=check,
    )


def staged_gitlinks() -> set[str]:
    raw = git_run(
        "ls-files",
        "--cached",
        "-z",
        "--format=%(stage)%x09%(objectmode)%x09%(path)",
    ).stdout

    result: set[str] = set()

    for record in raw.split(b"\0"):
        if not record:
            continue

        stage, mode, path = record.split(
            b"\t",
            2,
        )

        if stage == b"0" and mode == b"160000":
            result.add(os.fsdecode(path))

    return result


def gitmodules_oid() -> str | None:
    raw = git_run(
        "ls-files",
        "--cached",
        "-z",
        "--format=%(stage)%x09%(objectmode)%x09%(objectname)%x09%(path)",
        "--",
        ".gitmodules",
    ).stdout

    records = [record for record in raw.split(b"\0") if record]

    if not records:
        return None

    if len(records) != 1:
        return None

    stage, mode, oid, _ = records[0].split(
        b"\t",
        3,
    )

    if stage != b"0" or mode not in {
        b"100644",
        b"100755",
    }:
        return None

    return oid.decode("ascii")


def configured_paths(
    oid: str,
) -> set[str] | None:
    result = git_run(
        "config",
        "--blob",
        oid,
        "--get-regexp",
        r"^submodule\..*\.path$",
        check=False,
    )

    if result.returncode not in {
        0,
        1,
    }:
        return None

    paths: set[str] = set()

    for line in result.stdout.splitlines():
        try:
            _, value = line.split(
                maxsplit=1,
            )
        except ValueError:
            return None

        paths.add(os.fsdecode(value))

    return paths


gitlinks = staged_gitlinks()
oid = gitmodules_oid()

if oid is None:
    if gitlinks:
        for path in sorted(gitlinks):
            print(
                f"{path}: staged gitlink has no valid staged .gitmodules entry",
                file=sys.stderr,
            )

        raise SystemExit(1)

    raise SystemExit(0)

module_paths = configured_paths(oid)

if module_paths is None:
    print(
        ".gitmodules: unable to parse staged Git configuration",
        file=sys.stderr,
    )
    raise SystemExit(1)

failed = False

for path in sorted(gitlinks - module_paths):
    print(
        f"{path}: staged gitlink is missing from staged .gitmodules",
        file=sys.stderr,
    )
    failed = True

for path in sorted(module_paths - gitlinks):
    print(
        f".gitmodules: submodule path {path!r} has no staged gitlink",
        file=sys.stderr,
    )
    failed = True

raise SystemExit(1 if failed else 0)
