"""Isolated Git fixtures using the real Lefthook and CSpell executables."""

# cspell:ignore gpgsign
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]


class RepositoryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="common-hooks-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "consumer"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "CI": "true",
            "LEFTHOOK": "1",
        }
        for name in ("LEFTHOOK_CONFIG", "LEFTHOOK_EXCLUDE", "CSPELL_CONFIG"):
            self.env.pop(name, None)
        # Runtime installation belongs to Mise; these tests exercise wrappers
        # against the already installed binaries without downloading toolchains.
        self.executable(
            "mise",
            '#!/bin/sh\n[ "$1" = x ] && shift\n[ "$1" = -- ] && shift\nexec "$@"\n',
        )
        self.run_command("git", "init", "-q", "-b", "fixture")
        self.run_command("git", "config", "user.name", "Common hook tests")
        self.run_command("git", "config", "user.email", "common-tests@example.invalid")
        self.run_command("git", "config", "commit.gpgsign", "false")

    def executable(self, name, text):
        path = self.bin / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def run_command(self, *args, expected=0, cwd=None, env=None):
        result = subprocess.run(
            args,
            cwd=cwd or self.repo,
            env=env or self.env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if expected is not None:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def copy_common(self):
        shutil.copytree(
            SOURCE,
            self.repo,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".mise", "tests", "__pycache__"),
        )
        (self.repo / ".lefthook.yaml").unlink()

    def configure(self, config):
        self.write(".lefthook.json", json.dumps(config))

    def select(self, *configs):
        self.configure({"extends": ["lefthook.base.yaml", *configs]})

    def commit(self):
        self.run_command("git", "add", ".")
        self.run_command(
            "git", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture"
        )

    def dump(self):
        return json.loads(
            self.run_command("lefthook", "dump", "--format", "json").stdout
        )


def job_names(config):
    names = []

    def walk(jobs):
        for job in jobs:
            if "group" in job:
                walk(job["group"]["jobs"])
            else:
                names.append(job["name"])

    for hook in config.values():
        if isinstance(hook, dict) and "jobs" in hook:
            walk(hook["jobs"])
    return names
