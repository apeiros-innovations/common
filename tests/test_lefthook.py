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

    def record_tool(self, name):
        self.executable(
            name,
            f"#!{sys.executable}\n"
            "import json, os, sys\n"
            "from pathlib import Path\n"
            f"with Path({str(self.root / 'calls.jsonl')!r}).open('a') as log:\n"
            f"    log.write(json.dumps({{'tool': {name!r}, 'args': sys.argv[1:], "
            "'cwd': os.getcwd()}) + '\\n')\n",
        )

    def calls(self):
        log = self.root / "calls.jsonl"
        return (
            [json.loads(line) for line in log.read_text().splitlines()]
            if log.exists()
            else []
        )

    def test_script_globs_filter_before_starting_the_helper(self):
        self.select("lefthook.base.yaml", "lefthook/check-json.yaml")
        self.record_tool("python3")
        self.write("README.md", "Documentation\n")
        self.command("git", "add", "README.md")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(self.calls(), [])

        self.write("root file.json", "{}\n")
        self.write("nested/another.json", "{}\n")
        (self.repo / "linked.json").symlink_to("root file.json")
        self.command(
            "git", "add", "root file.json", "nested/another.json", "linked.json"
        )
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(
            set(self.calls()[0]["args"][1:]), {"root file.json", "nested/another.json"}
        )

    def test_json_filters_still_pass_invalid_content_to_validation(self):
        self.select("lefthook.base.yaml", "lefthook/check-json.yaml")
        for content in (b'{"broken":', b"\xff"):
            with self.subTest(content=content):
                (self.repo / "invalid.json").write_bytes(content)
                self.command("git", "add", "invalid.json")
                self.hook(
                    "run", "pre-commit", "--no-auto-install", "--no-tty", expected=1
                )

    def test_config_gate_and_file_glob_both_apply(self):
        self.select("lefthook.base.yaml", "lefthook/oxlint.yaml")
        self.record_tool("oxlint")
        self.write("source.js", "const value = 1;\n")
        self.command("git", "add", "source.js")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(self.calls(), [])
        self.write(".oxlintrc.json", "{}\n")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(
            self.calls()[0]["args"], ["--deny-warnings", "--", "source.js"]
        )
        self.command("git", "reset", "--quiet")
        self.write("README.md", "Documentation\n")
        self.command("git", "add", "README.md")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(len(self.calls()), 1)

    def test_cspell_config_gate_supports_untracked_and_nested_configs(self):
        # Remote consumers do not track common's check catalog. Avoid treating
        # this fixture's copied cspell.yaml check as a consumer spelling config.
        self.command(
            "git", "mv", "lefthook/cspell.yaml", "lefthook/spelling-check.yaml"
        )
        self.command("git", "rm", "lefthook/cspell-repository.yaml")
        self.select("lefthook.base.yaml", "lefthook/spelling-check.yaml")
        self.commit()
        self.record_tool("cspell")
        # Probe the native gate independently of shared configuration discovery.
        self.write(".lefthook/pre-commit/cspell", '#!/bin/sh\nexec cspell "$@"\n')
        self.write("source.txt", "Text\n")
        self.command("git", "add", "source.txt")
        self.write(".cspell.txt", "Not a config\n")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(self.calls(), [])
        for config in (
            ".cspell.yaml",
            ".config/cspell.json",
            ".vscode/cSpell.json",
            "nested/cspell.config.ts",
        ):
            with self.subTest(config=config):
                path = self.write(config, "{}\n")
                count = len(self.calls())
                self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
                self.assertEqual(len(self.calls()), count + 1)
                self.assertEqual(self.calls()[-1]["args"], ["source.txt"])
                path.unlink()
        self.write("package.json", '{"cspell": {}}\n')
        count = len(self.calls())
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(len(self.calls()), count + 1)

    def test_cspell_repository_uses_tracked_text_files(self):
        self.select("lefthook.base.yaml", "lefthook/cspell-repository.yaml")
        self.record_tool("cspell")
        self.write(".cspell.yaml", "version: '0.2'\n")
        self.write("nested/text file.txt", "Text\n")
        self.write(".hidden.txt", "Text\n")
        self.write("image.svg", "<svg/>\n")
        (self.repo / "binary.bin").write_bytes(b"\x00\xff")
        (self.repo / "linked.txt").symlink_to(".hidden.txt")
        self.commit()
        self.write("untracked.txt", "Text\n")
        self.hook("run", "pre-push", "--no-auto-install", "--no-tty")
        args = self.calls()[0]["args"]
        files = set(args[args.index("--") + 1 :])
        self.assertTrue(
            {"nested/text file.txt", ".hidden.txt", ".cspell.yaml"} <= files
        )
        self.assertTrue(
            {"image.svg", "binary.bin", "linked.txt", "untracked.txt"}.isdisjoint(files)
        )

    def test_explicit_missing_configs_fail_instead_of_skipping(self):
        for check, variable in (
            ("cspell", "CSPELL_CONFIG"),
            ("devskim", "DEVSKIM_OPTIONS_JSON"),
        ):
            with self.subTest(check=check):
                self.select("lefthook.base.yaml", f"lefthook/{check}.yaml")
                self.record_tool(check)
                self.env[variable] = "missing.json"
                self.write("source.py", "value = 1\n")
                self.command("git", "add", "source.py")
                result = self.hook(
                    "run", "pre-commit", "--no-auto-install", "--no-tty", expected=1
                )
                self.assertIn("not found", result.stdout + result.stderr)
                self.assertEqual(self.calls(), [])
                del self.env[variable]
                # only.run probes cannot see per-job env in Lefthook 2.1.15.
                # Explicit eligibility lets the helper validate a custom path.
                self.write(
                    ".config/lefthook-local.json",
                    json.dumps(
                        {
                            "pre-commit": {
                                "jobs": [
                                    {
                                        "name": "validate",
                                        "group": {
                                            "jobs": [
                                                {
                                                    "name": check,
                                                    "only": True,
                                                    "env": {variable: "missing.json"},
                                                }
                                            ]
                                        },
                                    }
                                ]
                            }
                        }
                    ),
                )
                result = self.hook(
                    "run", "pre-commit", "--no-auto-install", "--no-tty", expected=1
                )
                self.assertIn("not found", result.stdout + result.stderr)
                self.assertEqual(self.calls(), [])
                (self.repo / ".config/lefthook-local.json").unlink()

    def test_run_without_file_arguments_still_uses_glob_and_config_gates(self):
        self.select("lefthook.base.yaml", "lefthook/poetry-check.yaml")
        self.record_tool("poetry")
        self.write("source.py", "value = 1\n")
        self.command("git", "add", "source.py")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(self.calls(), [])
        self.write("pyproject.toml", "[project]\n")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(self.calls()[0]["args"], ["check", "--lock", "--strict"])
        self.command("git", "reset", "--quiet")
        self.write("README.md", "Documentation\n")
        self.command("git", "add", "README.md")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(len(self.calls()), 1)

    def test_astro_push_checks_skip_unrelated_files(self):
        self.record_tool("pnpm")
        self.write("public/asset.txt", "Asset\n")
        self.write("README.md", "Documentation\n")
        self.commit()
        self.select("lefthook.base.yaml", "lefthook/astro-check.yaml")
        self.hook(
            "run",
            "pre-push",
            "--file",
            "public/asset.txt",
            "--no-auto-install",
            "--no-tty",
        )
        self.assertEqual(self.calls(), [])
        self.write("package.json", "{}\n")
        for module in ("astro-check", "astro-build"):
            with self.subTest(module=module):
                self.select("lefthook.base.yaml", f"lefthook/{module}.yaml")
                count = len(self.calls())
                self.hook(
                    "run",
                    "pre-push",
                    "--file",
                    "README.md",
                    "--no-auto-install",
                    "--no-tty",
                )
                self.assertEqual(len(self.calls()), count)
                self.hook(
                    "run",
                    "pre-push",
                    "--file",
                    "public/asset.txt",
                    "--no-auto-install",
                    "--no-tty",
                )
                self.assertEqual(len(self.calls()), count + 1)
                self.assertEqual(self.calls()[-1]["tool"], "pnpm")

    def test_go_module_gate_preserves_tests_for_asset_changes(self):
        self.select("lefthook.base.yaml", "lefthook/go-test.yaml")
        self.record_tool("go")
        self.write("testdata/asset.txt", "Asset\n")
        self.commit()
        self.hook(
            "run",
            "pre-push",
            "--file",
            "testdata/asset.txt",
            "--no-auto-install",
            "--no-tty",
        )
        self.assertEqual(self.calls(), [])
        self.write("go.mod", "module example.invalid/fixture\n")
        self.commit()
        self.hook(
            "run",
            "pre-push",
            "--file",
            "testdata/asset.txt",
            "--no-auto-install",
            "--no-tty",
        )
        self.assertEqual(self.calls()[0]["args"], ["test", "./..."])

    def test_native_iac_formatting_filters_extensions_caches_and_symlinks(self):
        self.select(
            "lefthook.base.yaml",
            "lefthook/opentofu-fmt.yaml",
            "lefthook/terragrunt-fmt.yaml",
        )
        self.record_tool("tofu")
        self.record_tool("terragrunt")
        for path in (
            "root.tf",
            "nested/space name.tofu",
            "root.tftest.hcl",
            "terragrunt.hcl",
            "nested/unit.hcl",
            "README.md",
            ".terraform/cache.tf",
            ".terragrunt-cache/cache.hcl",
            ".terraform.lock.hcl",
            ".tflint.hcl",
        ):
            self.write(path, "# Text\n")
        (self.repo / "binary.tf").write_bytes(b"\x00\xff")
        (self.repo / "linked.tf").symlink_to("root.tf")
        self.command("git", "add", ".")
        self.hook("run", "pre-commit", "--no-auto-install", "--no-tty")
        self.assertEqual(
            {tuple(call["args"]) for call in self.calls() if call["tool"] == "tofu"},
            {
                ("fmt", "root.tf"),
                ("fmt", "nested/space name.tofu"),
                ("fmt", "root.tftest.hcl"),
            },
        )
        self.assertEqual(
            {
                tuple(call["args"])
                for call in self.calls()
                if call["tool"] == "terragrunt"
            },
            {
                ("hcl", "fmt", "--file=terragrunt.hcl"),
                ("hcl", "fmt", "--file=nested/unit.hcl"),
            },
        )

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
