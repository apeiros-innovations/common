"""Test native Lefthook composition, execution, and staging in isolated Git repos."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
LEFTHOOK = os.environ.get("LEFTHOOK_BIN") or shutil.which("lefthook")
if not LEFTHOOK:
    raise RuntimeError(
        "These tests require Lefthook 2.1.15; install it or set LEFTHOOK_BIN"
    )


def leaves(jobs):
    for job in jobs:
        if "group" in job:
            yield from leaves(job["group"].get("jobs", []))
        else:
            yield job


def all_jobs(config):
    for hook in ("commit-msg", "pre-commit", "pre-push"):
        yield from leaves(config.get(hook, {}).get("jobs", []))


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="common-lefthook-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "consumer"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith(("LEFTHOOK_", "GIT_", "MISE_")):
                del self.env[key]
        self.env.update(
            PATH=str(self.bin) + os.pathsep + self.env.get("PATH", ""),
            LEFTHOOK_VERBOSE="0",
            LEFTHOOK_EXCLUDE="",
            CI="true",
            NO_COLOR="1",
        )
        # Config tests exercise real Lefthook and real helpers. Mise's tool
        # installation/version resolution is outside this suite's scope.
        self.executable(
            "mise",
            '#!/bin/sh\n[ "$1" = x ] && shift\n[ "$1" = -- ] && shift\nexec "$@"\n',
        )
        self.executable(
            "python3", "#!/bin/sh\nexec " + json.dumps(sys.executable) + ' "$@"\n'
        )
        self.command("git", "init", "-q", "-b", "fixture")
        self.command("git", "config", "user.name", "Hook fixture")
        self.command("git", "config", "user.email", "fixture@example.invalid")
        for path in SOURCE.glob("lefthook.*.yaml"):
            shutil.copy2(path, self.repo / path.name)
        shutil.copytree(SOURCE / "lefthook", self.repo / "lefthook")
        shutil.copytree(SOURCE / ".lefthook", self.repo / ".lefthook")
        self.write(".gitignore", "*.pyc\n__pycache__/\n")
        self.select("lefthook.base.yaml")
        self.commit()

    def command(self, *args, expected=0, cwd=None):
        result = subprocess.run(
            args,
            cwd=cwd or self.repo,
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def hook(self, *args, expected=0):
        return self.command(LEFTHOOK, *args, expected=expected)

    def write(self, path, content):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return target

    def executable(self, name, content):
        target = self.bin / name
        target.write_text(content)
        target.chmod(0o755)

    def select(self, *configs):
        self.write(".config/lefthook.json", json.dumps({"extends": list(configs)}))

    def commit(self):
        self.command("git", "add", ".")
        self.command(
            "git", "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Fixture"
        )

    def dump(self):
        return json.loads(self.hook("dump", "--format", "json").stdout)

    def test_every_module_and_preset_has_executable_jobs(self):
        paths = sorted(SOURCE.glob("lefthook.*.yaml")) + sorted(
            (SOURCE / "lefthook").glob("*.yaml")
        )
        for path in paths:
            relative = path.relative_to(SOURCE).as_posix()
            with self.subTest(config=relative):
                # Common includes the base; every other selection needs it once.
                self.select(
                    *(
                        []
                        if relative in {"lefthook.base.yaml", "lefthook.common.yaml"}
                        else ["lefthook.base.yaml"]
                    ),
                    relative,
                )
                self.hook("validate")
                config = self.dump()
                self.assertEqual(
                    [j["name"] for j in config["pre-commit"]["jobs"]],
                    ["format", "generate", "validate"],
                )
                if relative != "lefthook.base.yaml":
                    self.assertTrue(list(all_jobs(config)), "missing or empty module")

    def test_common_is_compatible_entrypoint_and_policies_are_opt_in(self):
        self.select("lefthook.common.yaml", "lefthook.go.yaml", "lefthook.github.yaml")
        names = [j["name"] for j in all_jobs(self.dump())]
        self.assertIn("format json", names)
        self.assertIn("go test", names)
        self.assertIn("actionlint", names)
        for name in [
            "cspell",
            "cspell repository",
            "commitlint",
            "signed commits",
            "editorconfig",
        ]:
            self.assertNotIn(name, names)
        self.select(
            "lefthook.base.yaml",
            "lefthook/cspell.yaml",
            "lefthook/commitlint.yaml",
            "lefthook/signed-commits.yaml",
        )
        self.assertEqual(
            {j["name"] for j in all_jobs(self.dump())},
            {"cspell", "commitlint", "signed commits"},
        )
        self.assertNotIn(
            "cspell repository", [j["name"] for j in all_jobs(self.dump())]
        )

    def test_all_presets_compose_without_duplicate_extensions(self):
        self.select(
            *[
                p.name
                for p in sorted(SOURCE.glob("lefthook.*.yaml"))
                if p.name != "lefthook.base.yaml"
            ]
        )
        names = [j["name"] for j in all_jobs(self.dump())]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(names), 62)

    def test_base_alone_skips_empty_phases(self):
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")

    def test_phase_order_and_failure_boundary(self):
        for phase in ["format", "generate", "validate"]:
            self.write(
                phase + ".json",
                json.dumps(
                    {
                        "pre-commit": {
                            "jobs": [
                                {
                                    "name": phase,
                                    "skip": False,
                                    "group": {
                                        "jobs": [
                                            {
                                                "name": "probe " + phase,
                                                "run": "printf '"
                                                + phase
                                                + "\\n' >> order.txt",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                ),
            )
        self.select(
            "lefthook.base.yaml", "validate.json", "generate.json", "format.json"
        )
        self.write("trigger.txt", "trigger\n")
        self.command("git", "add", "trigger.txt")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(
            (self.repo / "order.txt").read_text().splitlines(),
            ["format", "generate", "validate"],
        )
        (self.repo / "order.txt").unlink()
        self.write(
            ".config/lefthook-local.json",
            json.dumps(
                {
                    "pre-commit": {
                        "jobs": [
                            {
                                "name": "format",
                                "group": {
                                    "jobs": [{"name": "probe format", "run": "exit 1"}]
                                },
                            }
                        ]
                    }
                }
            ),
        )
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty", expected=1)
        self.assertFalse((self.repo / "order.txt").exists())

    def test_nested_job_override_preserves_other_checks(self):
        self.select("lefthook.common.yaml", "lefthook.github.yaml")
        self.write(
            ".config/lefthook-local.json",
            json.dumps(
                {
                    "pre-commit": {
                        "jobs": [
                            {
                                "name": "validate",
                                "group": {"jobs": [{"name": "zizmor", "skip": True}]},
                            }
                        ]
                    }
                }
            ),
        )
        jobs = {j["name"]: j for j in all_jobs(self.dump())}
        self.assertTrue(jobs["zizmor"]["skip"])
        self.assertNotIn("skip", jobs["actionlint"])
        self.assertIn("shellcheck", jobs)

    def test_real_remote_profile_and_leaf_resolve_scripts(self):
        remote = self.root / "remote"
        shutil.copytree(self.repo, remote)
        self.command("git", "tag", "v0.0.1", cwd=remote)
        # Selecting a profile and then a leaf tests the loader's directory rules.
        self.write(
            ".config/lefthook.json",
            json.dumps(
                {
                    "remotes": [
                        {
                            "git_url": str(remote),
                            "ref": "v0.0.1",
                            "configs": [
                                "lefthook.common.yaml",
                                "lefthook/check-json.yaml",
                            ],
                        }
                    ]
                }
            ),
        )
        for path in self.repo.glob("lefthook.*.yaml"):
            path.unlink()
        shutil.rmtree(self.repo / "lefthook")
        shutil.rmtree(self.repo / ".lefthook")
        self.hook("install")
        self.assertIn("check json", [j["name"] for j in all_jobs(self.dump())])
        self.write("space name.json", '{"valid": true}\n')
        self.command("git", "add", "space name.json")
        self.hook(
            "run", "pre-commit", "--job", "check json", "--no-auto-install", "--no-tty"
        )
        self.write("space name.json", '{"duplicate": 1, "duplicate": 2}\n')
        self.command("git", "add", "space name.json")
        result = self.hook(
            "run",
            "pre-commit",
            "--job",
            "check json",
            "--no-auto-install",
            "--no-tty",
            expected=1,
        )
        self.assertIn("duplicate key", result.stdout + result.stderr)

    def test_ci_checks_committed_files_with_no_staged_diff(self):
        self.select("lefthook.base.yaml", "lefthook/check-json.yaml")
        self.write("root file.json", '{"duplicate": 1, "duplicate": 2}\n')
        self.write("nested/another.json", '{"valid": true}\n')
        self.commit()
        self.assertEqual(
            self.command("git", "diff", "--cached", "--name-only").stdout, ""
        )
        result = self.hook(
            "run",
            "pre-commit",
            "--tag",
            "ci",
            "--all-files",
            "--no-stage-fixed",
            "--fail-on-changes",
            "--no-auto-install",
            "--no-tty",
            expected=1,
        )
        self.assertIn("duplicate key", result.stdout + result.stderr)

    def test_ci_formatting_fails_without_staging_and_ignores_untracked_files(self):
        self.select("lefthook.base.yaml", "lefthook/text-hygiene.yaml")
        self.write("root file.txt", "needs cleanup   \n")
        self.commit()
        self.write("untracked.txt", "leave alone   \n")
        original = self.command("git", "show", ":root file.txt").stdout
        self.hook(
            "run",
            "pre-commit",
            "--tag",
            "ci",
            "--all-files",
            "--no-stage-fixed",
            "--fail-on-changes",
            "--no-auto-install",
            "--no-tty",
            expected=1,
        )
        self.assertEqual(self.command("git", "show", ":root file.txt").stdout, original)
        self.assertEqual((self.repo / "root file.txt").read_text(), "needs cleanup\n")
        self.assertEqual((self.repo / "untracked.txt").read_text(), "leave alone   \n")

    def test_local_formatter_preserves_unstaged_hunks(self):
        self.select("lefthook.base.yaml", "lefthook/text-hygiene.yaml")
        self.write("sample.txt", "first\n" + "context\n" * 12 + "last\n")
        self.commit()
        self.write("sample.txt", "staged edit   \n" + "context\n" * 12 + "last\n")
        self.command("git", "add", "sample.txt")
        self.write(
            "sample.txt", "staged edit   \n" + "context\n" * 12 + "unstaged edit\n"
        )
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        staged = self.command("git", "show", ":sample.txt").stdout
        self.assertTrue(staged.startswith("staged edit\n"))
        self.assertNotIn("unstaged", staged)
        self.assertIn("unstaged edit", (self.repo / "sample.txt").read_text())

    def test_ci_tag_excludes_index_push_and_generation_checks(self):
        self.select(
            "lefthook.common.yaml",
            "lefthook.go.yaml",
            "lefthook.helm.yaml",
            "lefthook.opentofu.yaml",
            "lefthook.terragrunt.yaml",
            "lefthook/signed-commits.yaml",
            "lefthook/cspell-repository.yaml",
        )
        config = self.dump()
        for hook in ["commit-msg", "pre-push"]:
            self.assertFalse(
                any(
                    "ci" in j.get("tags", [])
                    for j in leaves(config.get(hook, {}).get("jobs", []))
                )
            )
        forbidden = {
            "mise lock",
            "git diff check",
            "check added large files",
            "betterleaks",
            "check forced ignored files",
            "shebang permissions",
            "golangci lint",
            "helm docs",
            "opentofu docs",
            "opentofu provider lock",
            "terragrunt provider lock",
        }
        for job in all_jobs(config):
            if job["name"] in forbidden:
                self.assertNotIn("ci", job.get("tags", []), job["name"])

    def test_mise_config_layout_locks_the_matching_file(self):
        self.select("lefthook.base.yaml", "lefthook/mise-lock.yaml")
        self.executable(
            "mise",
            '#!/bin/sh\n[ "$1" = lock ] || exit 2\nprintf "locked\\n" > "$FIXTURE_LOCKFILE"\n',
        )
        for config, lock in [
            (".config/mise.toml", ".config/mise.lock"),
            (".mise/config.toml", ".mise/mise.lock"),
        ]:
            with self.subTest(config=config):
                self.write(config, "[tools]\n")
                self.env["FIXTURE_LOCKFILE"] = lock
                self.command("git", "add", config)
                self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
                self.assertEqual(
                    self.command("git", "show", ":" + lock).stdout, "locked\n"
                )
                self.commit()
                self.write(lock, "developer changes\n")
                self.write(config, "[tools]\n# changed\n")
                self.command("git", "add", config)
                self.hook(
                    "run", "pre-commit", "--no-auto-install", "--no-tty", expected=1
                )
                self.assertEqual((self.repo / lock).read_text(), "developer changes\n")
                self.command("git", "restore", lock)


if __name__ == "__main__":
    unittest.main()
