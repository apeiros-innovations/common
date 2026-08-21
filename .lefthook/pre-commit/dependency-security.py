#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from enum import StrEnum
from pathlib import Path


class DependencySecurityError(RuntimeError):
    pass


class PackageManager(StrEnum):
    NPM = "npm"
    PNPM = "pnpm"
    YARN = "yarn"
    BUN = "bun"


LOCKFILE_BY_MANAGER = {
    PackageManager.NPM: "package-lock.json",
    PackageManager.PNPM: "pnpm-lock.yaml",
    PackageManager.YARN: "yarn.lock",
    PackageManager.BUN: "bun.lock",
}

MANAGER_BY_LOCKFILE = {
    lockfile: manager
    for manager, lockfile in LOCKFILE_BY_MANAGER.items()
}

OSV_LOCKFILES = {
    "conan.lock",
    "pubspec.lock",
    "mix.lock",
    "go.mod",
    "cabal.project.freeze",
    "stack.yaml.lock",
    "buildscript-gradle.lockfile",
    "gradle.lockfile",
    "pom.xml",
    "bun.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "deps.json",
    "packages.config",
    "packages.lock.json",
    "composer.lock",
    "Pipfile.lock",
    "poetry.lock",
    "pdm.lock",
    "pylock.toml",
    "uv.lock",
    "renv.lock",
    "Gemfile.lock",
    "gems.locked",
    "Cargo.lock",
}


def git_output(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args],
        stderr=subprocess.DEVNULL,
        text=True,
    ).strip()


def repository_root() -> Path:
    try:
        root = git_output(
            "rev-parse",
            "--show-toplevel",
        )
    except subprocess.CalledProcessError as error:
        raise DependencySecurityError(
            "not inside a Git repository"
        ) from error

    return Path(root)


def load_package_json(
    root: Path,
) -> dict[str, object]:
    path = root / "package.json"

    if not path.is_file(follow_symlinks=False):
        raise DependencySecurityError(
            "package.json does not exist at repository root"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)
    except json.JSONDecodeError as error:
        raise DependencySecurityError(
            f"{path}:{error.lineno}:{error.colno}: "
            f"{error.msg}"
        ) from error

    if not isinstance(data, dict):
        raise DependencySecurityError(
            f"{path}: expected a JSON object"
        )

    return data


def declared_package_manager(
    root: Path,
) -> PackageManager | None:
    path = root / "package.json"

    if not path.is_file(follow_symlinks=False):
        return None

    data = load_package_json(root)
    raw = data.get("packageManager")

    if raw is None:
        return None

    if not isinstance(raw, str) or not raw.strip():
        raise DependencySecurityError(
            f"{path}: packageManager must be a non-empty string"
        )

    name, separator, _ = raw.partition("@")

    if not separator:
        raise DependencySecurityError(
            f"{path}: packageManager must include a version, "
            f"for example \"pnpm@11.22.0\""
        )

    try:
        return PackageManager(name)
    except ValueError as error:
        supported = ", ".join(
            manager.value
            for manager in PackageManager
        )

        raise DependencySecurityError(
            f"{path}: unsupported packageManager "
            f"{name!r}; supported managers: {supported}"
        ) from error


def root_lockfiles(
    root: Path,
) -> dict[PackageManager, Path]:
    found: dict[PackageManager, Path] = {}

    for manager, filename in LOCKFILE_BY_MANAGER.items():
        path = root / filename

        if path.is_file(follow_symlinks=False):
            found[manager] = path

    return found


def detect_package_manager(
    root: Path,
) -> tuple[PackageManager, Path]:
    declared = declared_package_manager(root)
    lockfiles = root_lockfiles(root)

    if len(lockfiles) > 1:
        rendered = "\n".join(
            f"  {path.name}"
            for path in sorted(
                lockfiles.values(),
            )
        )

        raise DependencySecurityError(
            "multiple root JavaScript package-manager "
            f"lockfiles are tracked or present:\n{rendered}\n"
            "remove stale lockfiles before remediation"
        )

    if declared is not None:
        expected = root / LOCKFILE_BY_MANAGER[declared]

        if not expected.is_file(follow_symlinks=False):
            raise DependencySecurityError(
                "package.json declares "
                f"{declared.value!r} but "
                f"{expected.name!r} does not exist"
            )

        return declared, expected

    if len(lockfiles) == 1:
        manager, lockfile = next(
            iter(lockfiles.items())
        )

        print(
            "dependency-security: "
            f"inferred package manager {manager.value!r} "
            f"from {lockfile.name}; "
            "consider declaring packageManager in package.json",
            file=sys.stderr,
        )

        return manager, lockfile

    raise DependencySecurityError(
        "unable to determine JavaScript package manager; "
        "declare packageManager in package.json or provide "
        "exactly one supported root lockfile"
    )


def is_requirements_file(
    path: Path,
) -> bool:
    return (
        path.name.startswith("requirements")
        and path.suffix == ".txt"
    )


def is_osv_lockfile(
    path: Path,
) -> bool:
    if path.name in OSV_LOCKFILES:
        return True

    if is_requirements_file(path):
        return True

    if (
        path.name == "verification-metadata.xml"
        and path.parent.name == "gradle"
    ):
        return True

    return False


def lockfiles_for_package_json(
    package_json: Path,
) -> list[Path]:
    directory = package_json.parent

    found = [
        directory / filename
        for filename in MANAGER_BY_LOCKFILE
        if (
            directory / filename
        ).is_file(follow_symlinks=False)
    ]

    if len(found) > 1:
        rendered = ", ".join(
            path.name
            for path in sorted(found)
        )

        raise DependencySecurityError(
            f"{package_json}: multiple package-manager "
            f"lockfiles found: {rendered}"
        )

    return found


def scan_targets(
    paths: list[str],
) -> list[Path]:
    targets: set[Path] = set()

    for filename in paths:
        path = Path(filename)

        if not path.is_file(follow_symlinks=False):
            continue

        if path.name == "package.json":
            targets.update(
                lockfiles_for_package_json(path)
            )
            continue

        if is_osv_lockfile(path):
            targets.add(path)

    return sorted(targets)


def run_osv_scan(
    targets: list[Path],
) -> int:
    failed = False

    for target in targets:
        print(
            f"dependency-security: scanning {target}",
            file=sys.stderr,
        )

        result = subprocess.run(
            [
                "osv-scanner",
                "scan",
                "source",
                "--format=vertical",
                "--verbosity=error",
                "-L",
                str(target),
            ],
            check=False,
        )

        if result.returncode != 0:
            failed = True

    return 1 if failed else 0


def scan_repository(
    root: Path,
) -> int:
    result = subprocess.run(
        [
            "osv-scanner",
            "scan",
            "source",
            "--format=vertical",
            "--verbosity=error",
            "--recursive",
            str(root),
        ],
        check=False,
    )

    return result.returncode


def command_scan(
    root: Path,
    paths: list[str],
) -> int:
    if not paths:
        return scan_repository(root)

    targets = scan_targets(paths)

    if not targets:
        return 0

    return run_osv_scan(targets)


def command_detect(
    root: Path,
) -> int:
    manager, lockfile = detect_package_manager(root)

    print(
        f"package-manager={manager.value}"
    )
    print(
        f"lockfile={lockfile.relative_to(root)}"
    )

    return 0


def remediate_npm(
    root: Path,
    lockfile: Path,
) -> int:
    manifest = root / "package.json"

    if not manifest.is_file(follow_symlinks=False):
        raise DependencySecurityError(
            "npm remediation requires package.json"
        )

    print(
        "dependency-security: launching "
        "OSV guided remediation for npm",
        file=sys.stderr,
    )

    result = subprocess.run(
        [
            "osv-scanner",
            "fix",
            "--interactive",
            "-M",
            str(manifest),
            "-L",
            str(lockfile),
        ],
        cwd=root,
        check=False,
    )

    return result.returncode


def remediate_pnpm(
    root: Path,
) -> int:
    print(
        "dependency-security: launching "
        "pnpm interactive vulnerability remediation",
        file=sys.stderr,
    )

    result = subprocess.run(
        [
            "pnpm",
            "audit",
            "--fix=update",
            "--interactive",
        ],
        cwd=root,
        check=False,
    )

    return result.returncode


def remediate_yarn(
    root: Path,
) -> int:
    print(
        "dependency-security: OSV guided remediation "
        "does not support yarn.lock",
        file=sys.stderr,
    )
    print(
        "dependency-security: launching Yarn's "
        "interactive dependency upgrade interface; "
        "this is not vulnerability-specific remediation",
        file=sys.stderr,
    )

    result = subprocess.run(
        [
            "yarn",
            "upgrade-interactive",
        ],
        cwd=root,
        check=False,
    )

    return result.returncode


def command_remediate(
    root: Path,
) -> int:
    manager, lockfile = detect_package_manager(root)

    print(
        "dependency-security: "
        f"package manager: {manager.value}",
        file=sys.stderr,
    )
    print(
        "dependency-security: "
        f"lockfile: {lockfile.relative_to(root)}",
        file=sys.stderr,
    )

    match manager:
        case PackageManager.NPM:
            return remediate_npm(
                root,
                lockfile,
            )

        case PackageManager.PNPM:
            return remediate_pnpm(root)

        case PackageManager.YARN:
            return remediate_yarn(root)

        case PackageManager.BUN:
            raise DependencySecurityError(
                "Bun lockfiles are supported by OSV scanning, "
                "but automatic remediation is not configured"
            )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="dependency-security.py",
    )

    commands = result.add_subparsers(
        dest="command",
        required=True,
    )

    scan = commands.add_parser(
        "scan",
        help="scan dependency files with OSV-Scanner",
    )
    scan.add_argument(
        "paths",
        nargs="*",
        help=(
            "dependency files to scan; "
            "without paths the repository is scanned recursively"
        ),
    )

    commands.add_parser(
        "detect",
        help="detect the root JavaScript package manager",
    )

    commands.add_parser(
        "remediate",
        help="launch package-manager-specific remediation",
    )

    return result


def main() -> int:
    arguments = parser().parse_args()

    try:
        root = repository_root()

        match arguments.command:
            case "scan":
                return command_scan(
                    root,
                    arguments.paths,
                )

            case "detect":
                return command_detect(root)

            case "remediate":
                return command_remediate(root)

    except DependencySecurityError as error:
        print(
            f"dependency-security: {error}",
            file=sys.stderr,
        )
        return 2

    return 2


raise SystemExit(main())
