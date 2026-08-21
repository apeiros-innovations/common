#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
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


@dataclass(frozen=True, order=True)
class IssueKey:
    ecosystem: str
    package: str
    advisory_ids: tuple[str, ...]


@dataclass(frozen=True, order=True)
class Finding:
    issue: IssueKey
    version: str


@dataclass(frozen=True)
class ScanSummary:
    findings: frozenset[Finding]

    @property
    def issues(self) -> frozenset[IssueKey]:
        return frozenset(
            finding.issue
            for finding in self.findings
        )

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def resolution_count(self) -> int:
        return len(
            {
                (
                    finding.issue.ecosystem,
                    finding.issue.package,
                    finding.version,
                )
                for finding in self.findings
            }
        )

    def versions_for(
        self,
        issue: IssueKey,
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    finding.version
                    for finding in self.findings
                    if finding.issue == issue
                }
            )
        )


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    existed: bool
    data: bytes | None


LOCKFILE_BY_MANAGER = {
    PackageManager.NPM: "package-lock.json",
    PackageManager.PNPM: "pnpm-lock.yaml",
    PackageManager.YARN: "yarn.lock",
    PackageManager.BUN: "bun.lock",
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


def git_output(
    *args: str,
    cwd: Path | None = None,
) -> str:
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=cwd,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "git is not installed or is not available on PATH"
        ) from error


def repository_root() -> Path:
    try:
        return Path(
            git_output(
                "rev-parse",
                "--show-toplevel",
            )
        )
    except subprocess.CalledProcessError as error:
        raise DependencySecurityError(
            "not inside a Git repository"
        ) from error


def run_command(
    command: list[str],
    *,
    cwd: Path,
) -> int:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=False,
        ).returncode
    except FileNotFoundError as error:
        raise DependencySecurityError(
            f"{command[0]} is not installed "
            "or is not available on PATH"
        ) from error


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

    raw = load_package_json(root).get(
        "packageManager"
    )

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
    return {
        manager: path
        for manager, filename
        in LOCKFILE_BY_MANAGER.items()
        if (
            path := root / filename
        ).is_file(follow_symlinks=False)
    }


def detect_package_manager(
    root: Path,
) -> tuple[PackageManager, Path]:
    declared = declared_package_manager(root)
    lockfiles = root_lockfiles(root)

    if len(lockfiles) > 1:
        rendered = "\n".join(
            f"  {path.name}"
            for path in sorted(
                lockfiles.values()
            )
        )

        raise DependencySecurityError(
            "multiple root JavaScript package-manager "
            f"lockfiles are present:\n{rendered}\n"
            "remove stale lockfiles before remediation"
        )

    if declared is not None:
        expected = (
            root
            / LOCKFILE_BY_MANAGER[declared]
        )

        if not expected.is_file(
            follow_symlinks=False
        ):
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
            f"inferred package manager "
            f"{manager.value!r} from {lockfile.name}; "
            "consider declaring packageManager "
            "in package.json",
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
    return (
        path.name in OSV_LOCKFILES
        or (
            path.name
            == "verification-metadata.xml"
            and path.parent.name == "gradle"
        )
    )


def lockfiles_for_package_json(
    package_json: Path,
) -> list[Path]:
    directory = package_json.parent

    found = [
        directory / filename
        for filename
        in LOCKFILE_BY_MANAGER.values()
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

        if not path.is_file(
            follow_symlinks=False
        ):
            continue

        if path.name == "package.json":
            targets.update(
                lockfiles_for_package_json(path)
            )
        elif is_osv_lockfile(path):
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

        if result.returncode == 1:
            vulnerabilities_found = True
        elif result.returncode != 0:
            print(
                "dependency-security: "
                f"osv-scanner failed for {target} "
                f"with exit code {result.returncode}",
                file=sys.stderr,
            )
            scanner_error = True

    if scanner_error:
        return 2

    return (
        1
        if vulnerabilities_found
        else 0
    )


def scan_repository(
    root: Path,
) -> int:
    print(
        "dependency-security: scanning repository",
        file=sys.stderr,
    )

    try:
        return subprocess.run(
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
        ).returncode
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "osv-scanner is not installed "
            "or is not available on PATH"
        ) from error


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
            "vulnerability data with exit code "
            f"{result.returncode}"
        )

        if detail:
            message = f"{message}: {detail}"

        raise DependencySecurityError(
            message
        )

    try:
        data = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as error:
        raise DependencySecurityError(
            "osv-scanner returned invalid JSON"
        ) from error

    if not isinstance(data, dict):
        raise DependencySecurityError(
            "osv-scanner returned an unexpected "
            "JSON document"
        )

    return data


def vulnerability_groups(
    package_result: dict[str, Any],
) -> list[tuple[str, ...]]:
    groups = package_result.get(
        "groups",
        [],
    )
    normalized: list[tuple[str, ...]] = []

    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue

            raw_ids = group.get(
                "ids",
                [],
            )

            if not isinstance(
                raw_ids,
                list,
            ):
                continue

            ids = tuple(
                sorted(
                    {
                        identifier
                        for identifier in raw_ids
                        if (
                            isinstance(
                                identifier,
                                str,
                            )
                            and identifier
                        )
                    }
                )
            )

            if ids:
                normalized.append(
                    ids
                )

    if normalized:
        return normalized

    vulnerabilities = package_result.get(
        "vulnerabilities",
        [],
    )

    if not isinstance(
        vulnerabilities,
        list,
    ):
        return []

    for vulnerability in vulnerabilities:
        if not isinstance(
            vulnerability,
            dict,
        ):
            continue

        identifier = vulnerability.get(
            "id"
        )

        if (
            isinstance(
                identifier,
                str,
            )
            and identifier
        ):
            normalized.append(
                (identifier,)
            )

    return normalized


def summarize_osv_report(
    report: dict[str, Any],
) -> ScanSummary:
    findings: set[Finding] = set()
    results = report.get(
        "results",
        [],
    )

    if not isinstance(results, list):
        raise DependencySecurityError(
            "osv-scanner JSON results field "
            "is not a list"
        )

    for scan_result in results:
        if not isinstance(
            scan_result,
            dict,
        ):
            continue

        packages = scan_result.get(
            "packages",
            [],
        )

        if not isinstance(
            packages,
            list,
        ):
            continue

        for package_result in packages:
            if not isinstance(
                package_result,
                dict,
            ):
                continue

            package = package_result.get(
                "package",
                {},
            )

            if not isinstance(
                package,
                dict,
            ):
                continue

            name = package.get("name")
            version = package.get("version")
            ecosystem = package.get(
                "ecosystem"
            )

            if not all(
                isinstance(value, str)
                and value
                for value in (
                    name,
                    version,
                    ecosystem,
                )
            ):
                continue

            for advisory_ids in (
                vulnerability_groups(
                    package_result
                )
            ):
                findings.add(
                    Finding(
                        issue=IssueKey(
                            ecosystem=ecosystem,
                            package=name,
                            advisory_ids=(
                                advisory_ids
                            ),
                        ),
                        version=version,
                    )
                )

    return ScanSummary(
        findings=frozenset(
            findings
        )
    )


def scan_lockfile_summary(
    lockfile: Path,
    *,
    cwd: Path,
) -> ScanSummary:
    return summarize_osv_report(
        osv_json_report(
            lockfile,
            cwd=cwd,
        )
    )


def vulnerable_npm_packages(
    summary: ScanSummary,
) -> list[str]:
    return sorted(
        {
            finding.issue.package
            for finding in summary.findings
            if (
                finding.issue.ecosystem
                == "npm"
            )
        }
    )


def tracked_package_json_files(
    root: Path,
) -> list[Path]:
    try:
        result = subprocess.run(
            [
                "git",
                "ls-files",
                "-z",
                "--",
                "package.json",
                ":(glob)**/package.json",
            ],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise DependencySecurityError(
            "git is not installed or is not "
            "available on PATH"
        ) from error
    except subprocess.CalledProcessError as error:
        raise DependencySecurityError(
            "unable to enumerate tracked "
            "package.json files"
        ) from error

    paths = {
        root
        / Path(
            raw.decode("utf-8")
        )
        for raw in result.stdout.split(
            b"\0"
        )
        if raw
    }

    root_manifest = (
        root / "package.json"
    )

    if root_manifest.exists():
        paths.add(
            root_manifest
        )

    return sorted(paths)


def protected_remediation_files(
    root: Path,
    manager: PackageManager,
) -> list[Path]:
    paths = set(
        tracked_package_json_files(
            root
        )
    )

    if manager == PackageManager.PNPM:
        paths.add(
            root
            / "pnpm-workspace.yaml"
        )

    return sorted(paths)


def snapshot_file(
    path: Path,
) -> FileSnapshot:
    if not path.exists():
        return FileSnapshot(
            path=path,
            existed=False,
            data=None,
        )

    return FileSnapshot(
        path=path,
        existed=True,
        data=path.read_bytes(),
    )


def snapshot_files(
    paths: list[Path],
) -> dict[Path, FileSnapshot]:
    return {
        path: snapshot_file(path)
        for path in paths
    }


def snapshot_changed(
    snapshot: FileSnapshot,
) -> bool:
    if (
        snapshot.existed
        != snapshot.path.exists()
    ):
        return True

    if not snapshot.existed:
        return False

    return (
        snapshot.path.read_bytes()
        != snapshot.data
    )


def changed_snapshots(
    snapshots: dict[
        Path,
        FileSnapshot,
    ],
) -> list[Path]:
    return sorted(
        snapshot.path
        for snapshot
        in snapshots.values()
        if snapshot_changed(
            snapshot
        )
    )


def restore_snapshot(
    snapshot: FileSnapshot,
) -> None:
    if not snapshot.existed:
        if snapshot.path.exists():
            snapshot.path.unlink()
        return

    if snapshot.data is None:
        raise DependencySecurityError(
            f"unable to restore "
            f"{snapshot.path}: "
            "snapshot data is missing"
        )

    snapshot.path.write_bytes(
        snapshot.data
    )


def restore_snapshots(
    snapshots: dict[
        Path,
        FileSnapshot,
    ],
) -> None:
    for snapshot in snapshots.values():
        restore_snapshot(
            snapshot
        )


def print_scan_summary(
    label: str,
    summary: ScanSummary,
) -> None:
    print(
        "dependency-security: "
        f"{label}: "
        f"{summary.finding_count} "
        "vulnerability finding"
        f"{'' if summary.finding_count == 1 else 's'} "
        f"across {summary.resolution_count} "
        "vulnerable package resolution"
        f"{'' if summary.resolution_count == 1 else 's'}",
        file=sys.stderr,
    )


def format_issue(
    issue: IssueKey,
    summary: ScanSummary,
) -> str:
    versions = ", ".join(
        summary.versions_for(
            issue
        )
    )
    advisories = ", ".join(
        issue.advisory_ids
    )

    return (
        f"{issue.package}@{versions}: "
        f"{advisories}"
    )


def print_issues(
    title: str,
    issues: frozenset[IssueKey],
    summary: ScanSummary,
) -> None:
    if not issues:
        return

    print(
        f"dependency-security: {title}:",
        file=sys.stderr,
    )

    for issue in sorted(issues):
        print(
            f"  {format_issue(issue, summary)}",
            file=sys.stderr,
        )


def print_remediation_comparison(
    before: ScanSummary,
    after: ScanSummary,
) -> None:
    resolved = (
        before.issues
        - after.issues
    )
    remaining = (
        before.issues
        & after.issues
    )
    introduced = (
        after.issues
        - before.issues
    )
    net_reduction = (
        before.finding_count
        - after.finding_count
    )

    print(
        "dependency-security: remediation result:",
        file=sys.stderr,
    )
    print(
        f"  before: "
        f"{before.finding_count} findings",
        file=sys.stderr,
    )
    print(
        f"  after: "
        f"{after.finding_count} findings",
        file=sys.stderr,
    )
    print(
        f"  net reduction: "
        f"{net_reduction}",
        file=sys.stderr,
    )
    print(
        "  resolved advisory/package issues: "
        f"{len(resolved)}",
        file=sys.stderr,
    )
    print(
        "  remaining advisory/package issues: "
        f"{len(remaining)}",
        file=sys.stderr,
    )
    print(
        "  introduced advisory/package issues: "
        f"{len(introduced)}",
        file=sys.stderr,
    )

    print_issues(
        "resolved",
        resolved,
        before,
    )
    print_issues(
        "remaining after conservative remediation",
        remaining,
        after,
    )
    print_issues(
        "introduced",
        introduced,
        after,
    )


def remediation_exit_code_allowed(
    manager: PackageManager,
    returncode: int,
) -> bool:
    if manager in {
        PackageManager.NPM,
        PackageManager.PNPM,
    }:
        return returncode in {0, 1}

    if manager == PackageManager.YARN:
        return returncode == 0

    return False


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
        "pnpm lockfile vulnerability remediation",
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
    before: ScanSummary,
) -> int:
    packages = vulnerable_npm_packages(
        before
    )

    if not packages:
        print(
            "dependency-security: "
            "no vulnerable Yarn package "
            "resolutions found",
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


def apply_remediation(
    manager: PackageManager,
    root: Path,
    lockfile: Path,
    before: ScanSummary,
) -> int:
    match manager:
        case PackageManager.NPM:
            return remediate_npm(
                root,
                lockfile,
            )

        case PackageManager.PNPM:
            return remediate_pnpm(
                root
            )

        case PackageManager.YARN:
            return remediate_yarn(
                root,
                before,
            )

        case PackageManager.BUN:
            raise DependencySecurityError(
                "Bun lockfiles are supported "
                "by OSV scanning, but automatic "
                "remediation is not configured"
            )

    raise DependencySecurityError(
        f"unsupported package manager: "
        f"{manager}"
    )


def command_scan(
    root: Path,
    paths: list[str],
) -> int:
    if not paths:
        return scan_repository(
            root
        )

    targets = scan_targets(
        paths
    )

    if not targets:
        return 0

    return run_osv_scan(
        targets
    )


def command_detect(
    root: Path,
) -> int:
    manager, lockfile = (
        detect_package_manager(
            root
        )
    )

    print(
        f"package-manager={manager.value}"
    )
    print(
        f"lockfile="
        f"{lockfile.relative_to(root)}"
    )

    return 0


def command_remediate(
    root: Path,
) -> int:
    manager, lockfile = (
        detect_package_manager(
            root
        )
    )

    print(
        "dependency-security: "
        f"package manager: {manager.value}",
        file=sys.stderr,
    )
    print(
        "dependency-security: "
        f"lockfile: "
        f"{lockfile.relative_to(root)}",
        file=sys.stderr,
    )
    print(
        "dependency-security: guardrail: "
        "remediation may update the lockfile "
        "but must not modify dependency manifests "
        "or package-manager policy files",
        file=sys.stderr,
    )

    before = scan_lockfile_summary(
        lockfile,
        cwd=root,
    )

    print_scan_summary(
        "before remediation",
        before,
    )

    if before.finding_count == 0:
        print(
            "dependency-security: "
            "no remediation required",
            file=sys.stderr,
        )
        return 0

    protected_paths = (
        protected_remediation_files(
            root,
            manager,
        )
    )

    protected = snapshot_files(
        protected_paths
    )

    rollback = snapshot_files(
        sorted(
            set(protected_paths)
            | {lockfile}
        )
    )

    try:
        returncode = apply_remediation(
            manager,
            root,
            lockfile,
            before,
        )
    except DependencySecurityError:
        restore_snapshots(
            rollback
        )
        raise

    if not remediation_exit_code_allowed(
        manager,
        returncode,
    ):
        restore_snapshots(
            rollback
        )

        raise DependencySecurityError(
            f"{manager.value} remediation "
            f"failed with exit code {returncode}; "
            "repository dependency files were restored"
        )

    changed_protected = (
        changed_snapshots(
            protected
        )
    )

    if changed_protected:
        restore_snapshots(
            rollback
        )

        rendered = "\n".join(
            f"  {path.relative_to(root)}"
            for path in changed_protected
        )

        raise DependencySecurityError(
            "remediation attempted to modify "
            "protected dependency files:\n"
            f"{rendered}\n"
            "repository dependency files were restored; "
            "broader dependency upgrades belong to the "
            "repository dependency update workflow"
        )

    try:
        after = scan_lockfile_summary(
            lockfile,
            cwd=root,
        )
    except DependencySecurityError:
        restore_snapshots(
            rollback
        )
        raise

    print_scan_summary(
        "after remediation",
        after,
    )

    print_remediation_comparison(
        before,
        after,
    )

    introduced = (
        after.issues
        - before.issues
    )

    if introduced:
        restore_snapshots(
            rollback
        )

        raise DependencySecurityError(
            "remediation introduced new "
            "advisory/package issues; repository "
            "dependency files were restored"
        )

    if (
        after.finding_count
        > before.finding_count
    ):
        restore_snapshots(
            rollback
        )

        raise DependencySecurityError(
            "remediation increased the vulnerability "
            "finding count; repository dependency "
            "files were restored"
        )

    if (
        after.finding_count
        == before.finding_count
    ):
        if snapshot_changed(
            rollback[lockfile]
        ):
            restore_snapshots(
                rollback
            )

            print(
                "dependency-security: remediation "
                "changed dependency files without "
                "reducing vulnerabilities; changes "
                "were restored to avoid unrelated churn",
                file=sys.stderr,
            )
        else:
            print(
                "dependency-security: no vulnerabilities "
                "could be remediated within the current "
                "dependency constraints",
                file=sys.stderr,
            )

        print(
            "dependency-security: remaining findings "
            "require broader dependency updates or "
            "upstream fixes; leave those changes to the "
            "repository dependency update workflow",
            file=sys.stderr,
        )

        return 1

    if after.finding_count > 0:
        print(
            "dependency-security: conservative remediation "
            "reduced the vulnerability set, but unresolved "
            "findings remain for the repository dependency "
            "update workflow",
            file=sys.stderr,
        )

        return 1

    print(
        "dependency-security: all detected vulnerabilities "
        "were remediated within the existing dependency policy",
        file=sys.stderr,
    )

    return 0


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
        help=(
            "scan dependency files "
            "with OSV-Scanner"
        ),
    )
    scan.add_argument(
        "paths",
        nargs="*",
        help=(
            "dependency files to scan; "
            "without paths the repository "
            "is scanned recursively"
        ),
    )

    commands.add_parser(
        "detect",
        help=(
            "detect the root JavaScript "
            "package manager"
        ),
    )

    commands.add_parser(
        "remediate",
        help=(
            "apply conservative automatic "
            "dependency remediation and compare "
            "OSV findings before and after"
        ),
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
                return command_detect(
                    root
                )

            case "remediate":
                return command_remediate(
                    root
                )

    except DependencySecurityError as error:
        print(
            f"dependency-security: {error}",
            file=sys.stderr,
        )
        return 2

    return 2


raise SystemExit(main())
