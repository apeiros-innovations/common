#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Any


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
    "requirements.txt",
    "pdm.lock",
    "pylock.toml",
    "uv.lock",
    "renv.lock",
    "Gemfile.lock",
    "gems.locked",
    "Cargo.lock",
}


def git_output(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "git is not installed or is not available on PATH"
        ) from error


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


def run_command(
    command: list[str],
    *,
    cwd: Path,
) -> int:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError as error:
        raise DependencySecurityError(
            f"{command[0]} is not installed or is not available on PATH"
        ) from error

    return result.returncode


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

    name, separator, version = raw.partition("@")

    if not separator or not version:
        raise DependencySecurityError(
            f"{path}: packageManager must include a version, "
            'for example "pnpm@11.22.0"'
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
            for path in sorted(lockfiles.values())
        )

        raise DependencySecurityError(
            "multiple root JavaScript package-manager "
            f"lockfiles are present:\n{rendered}\n"
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


def is_osv_lockfile(
    path: Path,
) -> bool:
    if path.name in OSV_LOCKFILES:
        return True

    return (
        path.name == "verification-metadata.xml"
        and path.parent.name == "gradle"
    )


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
    vulnerabilities_found = False
    scanner_error = False

    for target in targets:
        print(
            f"dependency-security: scanning {target}",
            file=sys.stderr,
        )

        try:
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
        except FileNotFoundError as error:
            raise DependencySecurityError(
                "osv-scanner is not installed "
                "or is not available on PATH"
            ) from error

        match result.returncode:
            case 0:
                pass

            case 1:
                vulnerabilities_found = True

            case _:
                print(
                    "dependency-security: "
                    f"osv-scanner failed for {target} "
                    f"with exit code {result.returncode}",
                    file=sys.stderr,
                )
                scanner_error = True

    if scanner_error:
        return 2

    if vulnerabilities_found:
        return 1

    return 0


def scan_repository(
    root: Path,
) -> int:
    print(
        "dependency-security: scanning repository",
        file=sys.stderr,
    )

    try:
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
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "osv-scanner is not installed "
            "or is not available on PATH"
        ) from error

    return result.returncode


def osv_json_report(
    lockfile: Path,
    *,
    cwd: Path,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "osv-scanner",
                "scan",
                "source",
                "--format=json",
                "--verbosity=error",
                "-L",
                str(lockfile),
            ],
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "osv-scanner is not installed "
            "or is not available on PATH"
        ) from error

    if result.returncode not in {0, 1}:
        detail = result.stderr.strip()

        message = (
            "osv-scanner failed while collecting "
            f"vulnerability data with exit code {result.returncode}"
        )

        if detail:
            message = f"{message}: {detail}"

        raise DependencySecurityError(message)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise DependencySecurityError(
            "osv-scanner returned invalid JSON"
        ) from error

    if not isinstance(data, dict):
        raise DependencySecurityError(
            "osv-scanner returned an unexpected JSON document"
        )

    return data


def vulnerable_npm_packages(
    lockfile: Path,
    *,
    cwd: Path,
) -> list[str]:
    report = osv_json_report(
        lockfile,
        cwd=cwd,
    )

    names: set[str] = set()

    results = report.get("results", [])

    if not isinstance(results, list):
        raise DependencySecurityError(
            "osv-scanner JSON results field is not a list"
        )

    for scan_result in results:
        if not isinstance(scan_result, dict):
            continue

        packages = scan_result.get("packages", [])

        if not isinstance(packages, list):
            continue

        for package_result in packages:
            if not isinstance(package_result, dict):
                continue

            vulnerabilities = package_result.get(
                "vulnerabilities",
                [],
            )

            if not isinstance(vulnerabilities, list):
                continue

            if not vulnerabilities:
                continue

            package = package_result.get(
                "package",
                {},
            )

            if not isinstance(package, dict):
                continue

            if package.get("ecosystem") != "npm":
                continue

            name = package.get("name")

            if isinstance(name, str) and name:
                names.add(name)

    return sorted(names)


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
    print(
        "dependency-security: applying "
        "OSV in-place remediation for npm",
        file=sys.stderr,
    )

    return run_command(
        [
            "osv-scanner",
            "fix",
            "--strategy=in-place",
            "--no-introduce",
            "-L",
            str(lockfile),
        ],
        cwd=root,
    )


def remediate_pnpm(
    root: Path,
) -> int:
    print(
        "dependency-security: applying "
        "pnpm vulnerability remediation",
        file=sys.stderr,
    )

    return run_command(
        [
            "pnpm",
            "audit",
            "--fix=update",
        ],
        cwd=root,
    )


def remediate_yarn(
    root: Path,
    lockfile: Path,
) -> int:
    print(
        "dependency-security: identifying vulnerable "
        "Yarn package resolutions with OSV",
        file=sys.stderr,
    )

    packages = vulnerable_npm_packages(
        lockfile,
        cwd=root,
    )

    if not packages:
        print(
            "dependency-security: "
            "no vulnerable Yarn package resolutions found",
            file=sys.stderr,
        )
        return 0

    print(
        "dependency-security: re-resolving "
        f"{len(packages)} vulnerable package"
        f"{'' if len(packages) == 1 else 's'} "
        "within existing dependency constraints:",
        file=sys.stderr,
    )

    for package in packages:
        print(
            f"  {package}",
            file=sys.stderr,
        )

    return run_command(
        [
            "yarn",
            "up",
            "-R",
            *packages,
        ],
        cwd=root,
    )


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
            return remediate_yarn(
                root,
                lockfile,
            )

        case PackageManager.BUN:
            raise DependencySecurityError(
                "Bun lockfiles are supported by OSV scanning, "
                "but automatic remediation is not configured"
            )

    raise DependencySecurityError(
        f"unsupported package manager: {manager}"
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
        help="apply conservative automatic dependency remediation",
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
