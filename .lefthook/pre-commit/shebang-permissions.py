#!/usr/bin/env python3

import os
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexEntry:
    stage: str
    mode: str
    oid: str


def git_output(*args: str) -> bytes:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
    )


def read_prefix(oid: str, length: int = 2) -> bytes:
    process = subprocess.Popen(
        ["git", "cat-file", "blob", oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    if process.stdout is None:
        raise RuntimeError(f"unable to read Git object {oid}")

    try:
        return process.stdout.read(length)
    finally:
        process.stdout.close()
        process.wait()


def load_index_entries(paths: list[str]) -> dict[str, list[IndexEntry]]:
    if not paths:
        return {}

    raw = git_output(
        "ls-files",
        "--cached",
        "-z",
        "--format=%(stage)%x09%(objectmode)%x09%(objectname)%x09%(path)",
        "--",
        *paths,
    )

    entries: dict[str, list[IndexEntry]] = defaultdict(list)

    for record in raw.split(b"\0"):
        if not record:
            continue

        stage, mode, oid, path = record.split(b"\t", 3)

        entries[os.fsdecode(path)].append(
            IndexEntry(
                stage=stage.decode("ascii"),
                mode=mode.decode("ascii"),
                oid=oid.decode("ascii"),
            )
        )

    return dict(entries)


paths = sys.argv[1:]
entries_by_path = load_index_entries(paths)

failed = False
make_executable: list[str] = []

for filename in paths:
    entries = entries_by_path.get(filename, [])

    if not entries:
        continue

    if len(entries) != 1:
        print(
            f"{filename}: index contains multiple stages; "
            "resolve the conflict before checking permissions",
            file=sys.stderr,
        )
        failed = True
        continue

    entry = entries[0]

    if entry.stage != "0":
        print(
            f"{filename}: index entry is at stage {entry.stage}; "
            "resolve the conflict before checking permissions",
            file=sys.stderr,
        )
        failed = True
        continue

    if entry.mode not in {"100644", "100755"}:
        continue

    has_shebang = read_prefix(entry.oid) == b"#!"

    if has_shebang and entry.mode == "100644":
        print(
            f"{filename}:1: shebang script has index mode 100644; "
            "setting executable mode 100755",
            file=sys.stderr,
        )

        path = Path(filename)

        if path.is_file(follow_symlinks=False):
            path.chmod(path.stat().st_mode | 0o111)

        make_executable.append(filename)
        continue

    if not has_shebang and entry.mode == "100755":
        print(
            f"{filename}:1: executable text file has index mode 100755 "
            "but does not begin with a shebang",
            file=sys.stderr,
        )
        failed = True

if make_executable:
    subprocess.run(
        [
            "git",
            "update-index",
            "--chmod=+x",
            "--",
            *make_executable,
        ],
        check=True,
    )

raise SystemExit(1 if failed else 0)
