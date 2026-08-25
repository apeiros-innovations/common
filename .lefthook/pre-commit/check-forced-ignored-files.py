#!/usr/bin/env python3

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Sequence

DS_STORE: Final = ".DS_Store"
DS_STORE_PATHS: Final = (
    ":(literal).DS_Store",
    ":(glob)**/.DS_Store",
)


class HookError(RuntimeError):
    """A user-actionable hook failure."""


@dataclass(frozen=True, slots=True)
class IgnoreMatch:
    source: str
    line: str
    pattern: str
    path: str


def run_git(
    *args: str,
    cwd: Path | None = None,
    input_data: bytes | None = None,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess[bytes]:
    """Run Git and convert failures into concise hook diagnostics."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as error:
        raise HookError(f"unable to execute git: {error}") from error

    if result.returncode not in allowed_returncodes:
        detail = os.fsdecode(result.stderr).strip()
        command = shlex.join(("git", *args))
        message = f"{command} failed with exit status {result.returncode}"

        if detail:
            message = f"{message}: {detail}"

        raise HookError(message)

    return result


def nul_fields(value: bytes) -> list[bytes]:
    """Split NUL-delimited Git output."""
    if not value:
        return []

    return value.removesuffix(b"\0").split(b"\0")


def repository_root() -> Path:
    result = run_git(
        "rev-parse",
        "--show-toplevel",
    )
    raw_path = result.stdout.removesuffix(b"\n").removesuffix(b"\r")

    return Path(os.fsdecode(raw_path))


def tracked_paths(root: Path) -> list[bytes]:
    result = run_git(
        "ls-files",
        "--cached",
        "-z",
        cwd=root,
    )

    return nul_fields(result.stdout)


def untracked_ds_store_paths(
    root: Path,
) -> set[bytes]:
    """Find ignored and non-ignored untracked .DS_Store files."""
    paths: set[bytes] = set()

    for extra_arguments in (
        ("--others", "--exclude-standard"),
        (
            "--others",
            "--ignored",
            "--exclude-standard",
        ),
    ):
        result = run_git(
            "ls-files",
            "-z",
            *extra_arguments,
            "--",
            *DS_STORE_PATHS,
            cwd=root,
        )
        paths.update(nul_fields(result.stdout))

    return paths


def remove_ds_store_files(
    root: Path,
    tracked: Sequence[bytes],
) -> None:
    """Remove .DS_Store files and stage tracked deletions."""
    tracked_ds_store = {
        path for path in tracked if PurePosixPath(os.fsdecode(path)).name == DS_STORE
    }

    discovered = untracked_ds_store_paths(root) | tracked_ds_store

    for relative_raw in sorted(discovered):
        relative = os.fsdecode(relative_raw)
        path = root / relative

        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise HookError(f"unable to remove {relative}: {error}") from error

        print(
            f"removed macOS metadata: {relative}",
            file=sys.stderr,
        )

    if not tracked_ds_store:
        return

    pathspecs = b"".join(path + b"\0" for path in sorted(tracked_ds_store))

    # Stage removal of tracked or force-added copies.
    run_git(
        "add",
        "-u",
        "--pathspec-from-file=-",
        "--pathspec-file-nul",
        cwd=root,
        input_data=pathspecs,
    )


def added_paths(
    root: Path,
    requested_paths: Sequence[str],
) -> list[bytes]:
    """Return newly added staged paths within the hook input."""
    if not requested_paths:
        return []

    # Treat hook arguments as literal filenames rather than
    # allowing Git pathspec metacharacters.
    literal_pathspecs = [f":(top,literal){path}" for path in requested_paths]

    result = run_git(
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=A",
        "-z",
        "--",
        *literal_pathspecs,
        cwd=root,
    )

    return nul_fields(result.stdout)


def tracked_gitignores(
    tracked: Sequence[bytes],
) -> set[bytes]:
    return {
        path
        for path in tracked
        if PurePosixPath(os.fsdecode(path)).name == ".gitignore"
    }


def parse_ignore_matches(
    output: bytes,
) -> list[IgnoreMatch]:
    fields = nul_fields(output)

    if len(fields) % 4 != 0:
        raise HookError("git check-ignore returned malformed verbose output")

    matches: list[IgnoreMatch] = []

    for index in range(0, len(fields), 4):
        (
            source,
            line,
            pattern,
            path,
        ) = fields[index : index + 4]

        matches.append(
            IgnoreMatch(
                source=os.fsdecode(source),
                line=line.decode(
                    "ascii",
                    errors="replace",
                ),
                pattern=os.fsdecode(pattern),
                path=os.fsdecode(path),
            )
        )

    return matches


def forced_ignored_additions(
    root: Path,
    added: Sequence[bytes],
    gitignores: set[bytes],
) -> list[IgnoreMatch]:
    if not added or not gitignores:
        return []

    result = run_git(
        "check-ignore",
        "--no-index",
        "--verbose",
        "-z",
        "--stdin",
        cwd=root,
        input_data=b"".join(path + b"\0" for path in added),
        allowed_returncodes=frozenset({0, 1}),
    )

    matches = parse_ignore_matches(result.stdout)
    tracked_sources = {os.fsdecode(path) for path in gitignores}

    return [
        match
        for match in matches
        if (match.source in tracked_sources and not match.pattern.startswith("!"))
    ]


def main(argv: Sequence[str]) -> int:
    try:
        root = repository_root()
        tracked = tracked_paths(root)
        remove_ds_store_files(
            root,
            tracked,
        )
        tracked = tracked_paths(root)

        matches = forced_ignored_additions(
            root,
            added_paths(root, argv),
            tracked_gitignores(tracked),
        )
    except HookError as error:
        print(
            f"check-forced-ignored-files: {error}",
            file=sys.stderr,
        )
        return 1

    for match in matches:
        print(
            f"{match.path}: force-added despite tracked "
            f"ignore rule {match.source}:{match.line}: "
            f"{match.pattern}",
            file=sys.stderr,
        )

    return 1 if matches else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
