#!/usr/bin/env python3

import subprocess
import sys

ZERO_OID_SHA1 = "0" * 40
ZERO_OID_SHA256 = "0" * 64


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def is_zero_oid(oid: str) -> bool:
    return oid in {
        ZERO_OID_SHA1,
        ZERO_OID_SHA256,
    }


def peel_commit(
    oid: str,
) -> str | None:
    try:
        return git_output(
            "rev-parse",
            "--verify",
            f"{oid}^{{commit}}",
        )
    except subprocess.CalledProcessError:
        return None


def outgoing_commits(
    remote_name: str,
    local_oid: str,
    remote_oid: str,
) -> list[str]:
    local_commit = peel_commit(local_oid)

    if local_commit is None:
        return []

    if is_zero_oid(remote_oid):
        output = git_output(
            "rev-list",
            local_commit,
            "--not",
            f"--remotes={remote_name}",
        )
    else:
        remote_commit = peel_commit(remote_oid)

        if remote_commit is None:
            output = git_output(
                "rev-list",
                local_commit,
                "--not",
                f"--remotes={remote_name}",
            )
        else:
            output = git_output(
                "rev-list",
                f"{remote_commit}..{local_commit}",
            )

    return output.splitlines() if output else []


def has_signature(
    commit: str,
) -> bool:
    raw = subprocess.check_output(
        [
            "git",
            "cat-file",
            "commit",
            commit,
        ],
        stderr=subprocess.DEVNULL,
    )

    headers, _, _ = raw.partition(b"\n\n")

    return any(
        line.startswith(
            (
                b"gpgsig ",
                b"gpgsig-sha256 ",
            )
        )
        for line in headers.splitlines()
    )


def describe(commit: str) -> str:
    return git_output(
        "show",
        "-s",
        "--format=%h %s",
        commit,
    )


remote_name = sys.argv[1] if len(sys.argv) > 1 else "origin"

failed = False
checked: set[str] = set()

for line in sys.stdin:
    fields = line.split()

    if len(fields) != 4:
        continue

    (
        local_ref,
        local_oid,
        remote_ref,
        remote_oid,
    ) = fields

    if is_zero_oid(local_oid):
        continue

    if not local_ref.startswith("refs/heads/"):
        continue

    for commit in outgoing_commits(
        remote_name,
        local_oid,
        remote_oid,
    ):
        if commit in checked:
            continue

        checked.add(commit)

        if has_signature(commit):
            continue

        print(
            f"{remote_ref}: unsigned outgoing commit: {describe(commit)}",
            file=sys.stderr,
        )

        failed = True

if failed:
    print(
        "sign the commits before pushing; "
        "remote signed-commit rules remain authoritative",
        file=sys.stderr,
    )

raise SystemExit(1 if failed else 0)
