"""Regression coverage for real CSpell config resolution and file selection."""

# cspell:ignore kumitatezorp misspelledwordzorp
import json

from support import SOURCE, RepositoryTest


class CSpellTests(RepositoryTest):
    def spell(self, *files, expected=0):
        return self.run_command(
            "bash", str(SOURCE / ".lefthook/lib/cspell"), *files, expected=expected
        )

    def test_shared_defaults_without_project_config(self):
        self.write("document.txt", "Apeiros\n")
        self.spell("document.txt")
        self.write("document.txt", "misspelledwordzorp\n")
        self.spell("document.txt", expected=1)

    def test_project_configs_recognize_their_own_words(self):
        for name in (
            ".cspell.yaml",
            ".config/cspell.yaml",
            ".vscode/cspell.json",
            "package.json",
        ):
            with self.subTest(config=name):
                settings = {"words": ["kumitatezorp"]}
                text = (
                    "words:\n  - kumitatezorp\n"
                    if name.endswith("yaml")
                    else json.dumps(
                        {"cspell": settings} if name == "package.json" else settings
                    )
                )
                config = self.write(name, text)
                self.write("document.txt", "kumitatezorp\n")
                self.spell(name, "document.txt")
                config.unlink()

    def test_cspell_dependency_is_not_a_configuration(self):
        self.write(
            "package.json", json.dumps({"devDependencies": {"cspell": "10.2.1"}})
        )
        self.write("document.txt", "Apeiros\n")
        self.spell("document.txt")

    def test_ambiguous_configuration_is_actionable(self):
        self.write(".cspell.yaml", "words:\n  - kumitatezorp\n")
        self.write("cspell.config.yaml", "words: []\n")
        result = self.spell(".cspell.yaml", expected=1)
        self.assertIn("multiple project configurations", result.stderr)
        self.assertIn("CSPELL_CONFIG", result.stderr)
        self.assertNotIn("Unknown word", result.stdout)

    def test_explicit_config_does_not_merge_discovered_configs(self):
        self.write(".cspell.yaml", "words:\n  - misspelledwordzorp\n")
        self.write("chosen.yaml", "words:\n  - kumitatezorp\n")
        self.env["CSPELL_CONFIG"] = "chosen.yaml"
        self.write("document.txt", "kumitatezorp\n")
        self.spell("chosen.yaml", "document.txt")
        self.write("document.txt", "misspelledwordzorp\n")
        self.spell("document.txt", expected=1)
        self.env["CSPELL_CONFIG"] = "does-not-exist.yaml"
        result = self.spell("document.txt", expected=1)
        self.assertIn("configuration not found", result.stderr)

    def test_nested_configuration_and_imports(self):
        self.write(".cspell.yaml", "words: []\n")
        self.write("docs/cspell.yaml", "import: ./words.yaml\n")
        self.write("docs/words.yaml", "words:\n  - kumitatezorp\n")
        self.write("docs/document.txt", "kumitatezorp\n")
        self.spell("docs/document.txt")
        self.write("document.txt", "kumitatezorp\n")
        self.spell("document.txt", expected=1)

    def test_parent_config_does_not_leak_into_consumer(self):
        (self.root / "cspell.yaml").write_text("words:\n  - misspelledwordzorp\n")
        self.write("document.txt", "misspelledwordzorp\n")
        self.spell("document.txt", expected=1)

    def test_project_ignore_paths_control_file_selection(self):
        self.write(".cspell.yaml", "ignorePaths:\n  - skip.txt\n")
        self.write("skip.txt", "misspelledwordzorp\n")
        self.spell("skip.txt")

    def test_literal_filenames_and_empty_input(self):
        self.write("document [one].txt", "misspelledwordzorp\n")
        self.spell("document [one].txt", expected=1)
        self.write("-document.txt", "This sentence is correct.\n")
        self.spell("-document.txt")
        self.spell()

    def test_repository_hook_checks_only_tracked_text(self):
        self.copy_common()
        self.select("lefthook/cspell-repository.yaml")
        self.write(".cspell.yaml", 'files: ["document.txt", "untracked.txt"]\n')
        self.write("document.txt", "This sentence is correct.\n")
        self.commit()
        self.write("untracked.txt", "misspelledwordzorp\n")
        self.run_command("lefthook", "run", "pre-push")
        self.run_command("git", "add", "untracked.txt")
        self.run_command("lefthook", "run", "pre-push", expected=1)
