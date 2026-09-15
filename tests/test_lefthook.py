"""Exercise native configuration composition and Git staging boundaries."""

# cspell:ignore kumitatezorp misspelledwordzorp
import json
import shutil

from support import SOURCE, RepositoryTest, job_names


class LefthookTests(RepositoryTest):
    def setUp(self):
        super().setUp()
        self.copy_common()

    def test_every_module_and_preset_loads(self):
        paths = sorted(SOURCE.glob("lefthook.*.yaml")) + sorted(
            (SOURCE / "lefthook").glob("*.yaml")
        )
        for path in paths:
            with self.subTest(config=path.name):
                selected = (
                    []
                    if path.name == "lefthook.base.yaml"
                    else [str(path.relative_to(SOURCE))]
                )
                self.select(*selected)
                self.run_command("lefthook", "validate")
                self.assertEqual(
                    [j["name"] for j in self.dump()["pre-commit"]["jobs"]],
                    ["generate", "format", "validate"],
                )

    def test_presets_compose_without_repeated_extensions(self):
        self.select(
            *[
                p.name
                for p in sorted(SOURCE.glob("lefthook.*.yaml"))
                if p.name != "lefthook.base.yaml"
            ]
        )
        names = job_names(self.dump())
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("opentofu docs", names)
        self.assertIn("go test", names)
        self.assertNotIn("cspell", names)
        self.assertNotIn("editorconfig", names)
        self.assertNotIn("commitlint", names)
        self.assertNotIn("signed commits", names)

    def test_common_and_cspell_are_independent(self):
        self.select("lefthook.common.yaml")
        self.assertFalse(any("cspell" in name for name in job_names(self.dump())))
        self.select("lefthook/cspell.yaml")
        self.assertEqual(job_names(self.dump()), ["cspell"])
        self.assertNotIn("pre-push", self.dump())
        self.select("lefthook/cspell.yaml", "lefthook/cspell-repository.yaml")
        self.assertEqual(set(job_names(self.dump())), {"cspell", "cspell repository"})

    def test_base_alone_runs_without_empty_group_errors(self):
        self.select()
        self.run_command("lefthook", "run", "pre-commit")

    def test_phase_order_and_failure_boundary(self):
        # Select modules in the opposite order to the execution phases.
        for phase in ("generate", "format", "validate"):
            self.write(
                f"{phase}.json",
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
                                                "run": f"printf '{phase}\\n' >> order.txt",
                                            }
                                        ]
                                    },
                                }
                            ]
                        }
                    }
                ),
            )
        self.select("validate.json", "format.json", "generate.json")
        self.write("trigger.txt", "trigger\n")
        self.run_command("git", "add", "trigger.txt")
        self.run_command("lefthook", "run", "pre-commit")
        self.assertEqual(
            (self.repo / "order.txt").read_text().splitlines(),
            ["generate", "format", "validate"],
        )
        (self.repo / "order.txt").unlink()
        self.write(
            ".lefthook-local.json",
            json.dumps(
                {
                    "pre-commit": {
                        "jobs": [
                            {
                                "name": "generate",
                                "group": {
                                    "jobs": [
                                        {"name": "probe generate", "run": "exit 1"}
                                    ]
                                },
                            }
                        ]
                    }
                }
            ),
        )
        self.run_command("lefthook", "run", "pre-commit", expected=1)
        self.assertFalse((self.repo / "order.txt").exists())

    def test_formatter_preserves_unstaged_hunks(self):
        self.select("lefthook/text-hygiene.yaml")
        self.write("document.txt", "first line\n" + "context\n" * 10 + "last line\n")
        self.commit()
        self.write(
            "document.txt", "first line changed   \n" + "context\n" * 10 + "last line\n"
        )
        self.run_command("git", "add", "document.txt")
        self.write(
            "document.txt",
            "first line changed   \n" + "context\n" * 10 + "last line unstaged\n",
        )
        self.run_command("lefthook", "run", "pre-commit")
        staged = self.run_command("git", "show", ":document.txt").stdout
        self.assertTrue(staged.startswith("first line changed\n"))
        self.assertNotIn("unstaged", staged)
        self.assertIn("last line unstaged", (self.repo / "document.txt").read_text())

    def test_remote_preset_then_individual_module_and_local_override(self):
        remote = self.root / "shared"
        shutil.copytree(self.repo, remote)
        # This isolated fixture publishes only to a local filesystem Git repo.
        self.commit()
        self.run_command("git", "add", ".", cwd=remote)
        self.run_command(
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "remote fixture",
            cwd=remote,
        )
        for path in self.repo.iterdir():
            if path.name != ".git":
                shutil.rmtree(path) if path.is_dir() else path.unlink()
        self.configure(
            {
                "remotes": [
                    {
                        "git_url": str(remote),
                        "ref": "fixture",
                        "configs": [
                            "lefthook.base.yaml",
                            "lefthook.common.yaml",
                            "lefthook/cspell.yaml",
                        ],
                    }
                ]
            }
        )
        self.run_command("lefthook", "install")
        self.assertIn("cspell", job_names(self.dump()))
        self.write(".cspell.yaml", "words:\n  - kumitatezorp\n")
        self.write("document.txt", "kumitatezorp\n")
        self.run_command("git", "add", "document.txt", ".cspell.yaml")
        self.run_command("lefthook", "run", "pre-commit", "--job", "cspell")
        self.write(
            ".lefthook-local.json",
            json.dumps(
                {
                    "pre-commit": {
                        "jobs": [
                            {
                                "name": "validate",
                                "group": {"jobs": [{"name": "cspell", "skip": True}]},
                            }
                        ]
                    }
                }
            ),
        )
        self.write("document.txt", "misspelledwordzorp\n")
        self.run_command("git", "add", "document.txt")
        self.run_command("lefthook", "run", "pre-commit", "--job", "cspell")

    def test_opentofu_generator_formats_and_stages_new_output(self):
        self.select("lefthook/terraform-docs.yaml")
        self.commit()
        self.write("main.tf", 'variable "example" {}\n')
        self.run_command("git", "add", "main.tf")
        self.executable(
            "terraform-docs", '#!/bin/sh\nprintf "unformatted\\n" > README.md\n'
        )
        self.executable(
            "oxfmt", '#!/bin/sh\nfor path do :; done\nprintf "formatted\\n" > "$path"\n'
        )
        # The fixture baseline includes README; remove it to simulate new output.
        self.run_command("git", "rm", "README.md")
        self.run_command("lefthook", "run", "pre-commit")
        self.assertEqual(
            self.run_command("git", "show", ":README.md").stdout, "formatted\n"
        )

    def test_generator_refuses_unstaged_output(self):
        self.select("lefthook/terraform-docs.yaml")
        self.commit()
        self.write("README.md", "uncommitted developer work\n")
        self.write("main.tf", 'variable "example" {}\n')
        self.run_command("git", "add", "main.tf")
        self.run_command("lefthook", "run", "pre-commit", expected=1)
        self.assertEqual(
            (self.repo / "README.md").read_text(), "uncommitted developer work\n"
        )
