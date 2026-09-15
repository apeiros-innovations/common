"""Verify catalog generation, ownership, and native local/remote configuration."""

import importlib.util
import json
import os
import shutil
import unittest

import tomllib
from support import SOURCE, RepositoryTest

SPEC = importlib.util.spec_from_file_location(
    "common_tools", SOURCE / ".lefthook/common-tools/sync.py"
)
TOOLS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOLS)
CATALOG = tomllib.loads((SOURCE / "tools/catalog.toml").read_text())
MISE = shutil.which("mise")


class ToolTests(RepositoryTest):
    def setUp(self):
        super().setUp()
        self.copy_common()

    def sync(self, *args, expected=0, cwd=None):
        return self.run_command(
            "lefthook", "run", "common-tools", "--", *args, expected=expected, cwd=cwd
        )

    def generated(self, root=None):
        return tomllib.loads(((root or self.repo) / TOOLS.OUTPUT).read_text())

    @unittest.skipUnless(MISE, "native Mise is required for the bootstrap integration")
    def test_native_mise_bootstrap_and_project_override(self):
        self.select("lefthook/cspell.yaml")
        project = self.write(
            ".mise/config.toml", (SOURCE / ".mise/config.toml").read_text()
        )
        env = {
            key: value
            for key, value in self.env.items()
            if not key.startswith("__MISE_")
        }
        env.update(
            {
                "PATH": os.path.dirname(MISE) + os.pathsep + os.defpath,
                "MISE_TRUSTED_CONFIG_PATHS": str(self.repo),
                "MISE_AUTO_INSTALL": "false",
            }
        )
        self.run_command(
            MISE,
            "--no-hooks",
            "x",
            "python@" + CATALOG["tools"]["python"],
            "aqua:evilmartians/lefthook@"
            + CATALOG["tools"]["aqua:evilmartians/lefthook"],
            "--",
            "lefthook",
            "run",
            "common-tools",
            env=env,
        )
        self.assertEqual(
            set(self.generated()["tools"]),
            {"python", "node", "npm:cspell", "aqua:evilmartians/lefthook"},
        )
        self.run_command(MISE, "run", "tools:sync", "--check", env=env)
        project.write_text(project.read_text() + '\n[tools]\nnode = "22.0.0"\n')
        resolved = json.loads(
            self.run_command(MISE, "ls", "--current", "--json", env=env).stdout
        )
        self.assertEqual([tool["version"] for tool in resolved["node"]], ["22.0.0"])

    def test_selection_deduplicates_and_removes_tools(self):
        self.select(
            "lefthook/cspell.yaml",
            "lefthook/cspell-repository.yaml",
            "lefthook/markdownlint.yaml",
        )
        self.sync()
        self.assertEqual(
            set(self.generated()["tools"]),
            {
                "python",
                "aqua:evilmartians/lefthook",
                "node",
                "npm:cspell",
                "npm:markdownlint-cli2",
            },
        )
        self.select()
        self.sync()
        self.assertEqual(
            set(self.generated()["tools"]), {"python", "aqua:evilmartians/lefthook"}
        )

    def test_checks_detect_drift_without_writing(self):
        self.select()
        self.sync("--check", expected=1)
        self.assertFalse((self.repo / TOOLS.OUTPUT).exists())
        self.sync()
        before = (self.repo / TOOLS.OUTPUT).read_bytes()
        self.select("lefthook/cspell.yaml")
        self.sync("--check", expected=1)
        self.assertEqual((self.repo / TOOLS.OUTPUT).read_bytes(), before)
        self.sync()
        catalog = self.repo / "tools/catalog.toml"
        catalog.write_text(
            catalog.read_text().replace(
                json.dumps(CATALOG["tools"]["npm:cspell"]), '"0.0.0"'
            )
        )
        self.sync("--check", expected=1)
        self.sync()
        self.assertEqual(self.generated()["tools"]["npm:cspell"], "0.0.0")

    def test_personal_overrides_are_excluded_and_tracked_overrides_are_used(self):
        self.select("lefthook/cspell.yaml")
        self.sync()
        before = (self.repo / TOOLS.OUTPUT).read_bytes()
        override = json.dumps(
            {
                "pre-commit": {
                    "jobs": [
                        {
                            "name": "validate",
                            "group": {
                                "jobs": [
                                    {
                                        "name": "personal formatter",
                                        "run": "true",
                                        "tags": ["common-tools:yamlfmt"],
                                    },
                                    {"name": "cspell", "skip": True},
                                ]
                            },
                        }
                    ]
                }
            }
        )
        self.write(".gitignore", "*lefthook-local*\n")
        for name in (".lefthook-local.json", ".config/lefthook-local.json"):
            with self.subTest(path=name):
                path = self.write(name, override)
                self.sync("--check")
                self.assertEqual((self.repo / TOOLS.OUTPUT).read_bytes(), before)
                self.assertEqual(path.read_text(), override)
                path.unlink()
        self.write(".lefthook-local.json", override)
        self.run_command("git", "add", "-f", ".lefthook-local.json")
        self.sync()
        self.assertIn("aqua:google/yamlfmt", self.generated()["tools"])
        # Execution overrides do not remove dependencies from a selected module.
        self.assertIn("npm:cspell", self.generated()["tools"])

    def test_project_configuration_and_unmanaged_output_are_protected(self):
        self.select("lefthook/cspell.yaml")
        project = self.write(".mise/config.toml", '[tools]\nnode = "24"\n')
        custom = self.write(".mise/conf.d/project.toml", '[env]\nPROJECT = "example"\n')
        old = self.write(str(TOOLS.OUTPUT), '[tools]\nnode = "22"\n')
        result = self.sync(expected=1)
        self.assertIn("is not generated", result.stdout + result.stderr)
        self.assertEqual(old.read_text(), '[tools]\nnode = "22"\n')
        old.unlink()
        self.sync()
        self.assertEqual(project.read_text(), '[tools]\nnode = "24"\n')
        self.assertEqual(custom.read_text(), '[env]\nPROJECT = "example"\n')

    def test_formatting_does_not_cause_drift(self):
        self.select("lefthook/cspell.yaml")
        self.sync()
        output = self.repo / TOOLS.OUTPUT
        output.write_text(output.read_text().replace('"node" =', "node ="))
        before = output.stat().st_mtime_ns
        self.sync("--check")
        self.sync()
        self.assertEqual(output.stat().st_mtime_ns, before)

    def test_linked_worktree_writes_its_own_configuration(self):
        self.select("lefthook/cspell.yaml")
        self.commit()
        linked = self.root / "linked"
        self.run_command("git", "worktree", "add", "-q", "-b", "linked", str(linked))
        self.sync(cwd=linked)
        self.assertIn("npm:cspell", self.generated(linked)["tools"])
        self.assertFalse((self.repo / TOOLS.OUTPUT).exists())

    def test_remote_uses_catalog_from_selected_revision(self):
        self.select()
        self.commit()
        remote = self.root / "shared"
        shutil.copytree(self.repo, remote)
        first = self.run_command("git", "rev-parse", "HEAD", cwd=remote).stdout.strip()
        self.run_command("git", "tag", "v1-fixture", first, cwd=remote)
        catalog = remote / "tools/catalog.toml"
        catalog.write_text(
            catalog.read_text().replace(
                json.dumps(CATALOG["tools"]["npm:cspell"]), '"0.0.0"'
            )
        )
        self.run_command("git", "add", "tools/catalog.toml", cwd=remote)
        self.run_command(
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "update catalog",
            cwd=remote,
        )
        second = self.run_command("git", "rev-parse", "HEAD", cwd=remote).stdout.strip()
        self.run_command("git", "tag", "v2-fixture", second, cwd=remote)
        for path in self.repo.iterdir():
            if path.name != ".git":
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        # A similarly named consumer catalog must not replace the remote one.
        self.write("tools/catalog.toml", "schema_version = 999\n")
        for revision, version in (
            ("v1-fixture", CATALOG["tools"]["npm:cspell"]),
            ("v2-fixture", "0.0.0"),
        ):
            with self.subTest(revision=revision):
                self.configure(
                    {
                        "remotes": [
                            {
                                "git_url": str(remote),
                                "ref": revision,
                                "configs": [
                                    "lefthook.base.yaml",
                                    "lefthook/cspell.yaml",
                                ],
                            }
                        ]
                    }
                )
                self.run_command("lefthook", "install")
                self.sync()
                self.assertEqual(self.generated()["tools"]["npm:cspell"], version)
                self.sync("--check")

    def test_catalog_options_and_runtime_dependencies_are_preserved(self):
        config = TOOLS.resolve(CATALOG, {"poetry", "devskim", "renovate"})
        self.assertIn("python", config["tools"])
        self.assertIn("aqua:astral-sh/uv", config["tools"])
        self.assertEqual(config["tools"]["npm:renovate"]["allow_builds"], ["re2"])
        self.assertEqual(config["env"]["DOTNET_CLI_TELEMETRY_OPTOUT"], "1")
        self.assertFalse(config["deps"]["poetry"]["auto"])
        self.assertEqual(tomllib.loads(TOOLS.render(config, [TOOLS.MARKER])), config)

    def test_catalog_errors_are_actionable(self):
        with self.assertRaisesRegex(TOOLS.ConfigurationError, "unknown tool group"):
            TOOLS.resolve(CATALOG, {"missing"})
        with self.assertRaisesRegex(TOOLS.ConfigurationError, "no catalog definition"):
            TOOLS.resolve(
                {
                    "schema_version": 1,
                    "tools": {},
                    "groups": {"broken": {"tools": ["missing"]}},
                },
                {"broken"},
            )
        conflicting = {
            "schema_version": 1,
            "tools": {},
            "groups": {
                "one": {"env": {"EXAMPLE": "one"}},
                "two": {"env": {"EXAMPLE": "two"}},
            },
        }
        with self.assertRaisesRegex(
            TOOLS.ConfigurationError, "conflicting group settings"
        ):
            TOOLS.resolve(conflicting, {"one", "two"})

    def test_every_module_declares_known_requirements(self):
        used = set()
        for path in sorted((SOURCE / "lefthook").glob("*.yaml")):
            with self.subTest(module=path.name):
                self.select(str(path.relative_to(SOURCE)))
                config = self.dump()
                groups = TOOLS.selected_groups(config)
                self.assertGreater(len(groups), 1)
                used.update(TOOLS.resolve(CATALOG, groups)["tools"])
        self.assertEqual(used, set(CATALOG["tools"]))
