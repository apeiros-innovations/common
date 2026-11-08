import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { selectFiles } from "../../.github/actions/lint-files/index.mjs";

const action = fileURLToPath(
  new URL("../../.github/actions/lint-files/index.mjs", import.meta.url),
);
function fixture(t, files) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "common-files-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  execFileSync("git", ["init", "--quiet", root]);
  for (const [name, content] of Object.entries(files)) {
    fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
    fs.writeFileSync(path.join(root, name), content);
  }
  execFileSync("git", ["add", "."], { cwd: root });
  return root;
}

test("each scope includes root and nested files and honors exclusions", (t) => {
  const root = fixture(t, {
    "root.yaml": "",
    ".github/workflows/ci.yml": "",
    "other.md": "",
    "charts/app/templates/config.yaml": "",
  });
  assert.deepEqual(
    selectFiles(root, ":(glob)**/*.yaml\n:(glob)**/*.yml\n:(glob,exclude)**/templates/**"),
    ["./.github/workflows/ci.yml", "./root.yaml"],
  );
  assert.deepEqual(selectFiles(root, ":(glob)**/*.md"), ["./other.md"]);
});

test("deleted files, symlinks, and untracked files are never passed to a linter", (t) => {
  const root = fixture(t, { "kept.yaml": "", "removed.yaml": "" });
  fs.unlinkSync(path.join(root, "removed.yaml"));
  fs.writeFileSync(path.join(root, "untracked.yaml"), "");
  fs.symlinkSync("kept.yaml", path.join(root, "link.yaml"));
  execFileSync("git", ["add", "link.yaml"], { cwd: root });
  assert.deepEqual(selectFiles(root, "*.yaml"), ["./kept.yaml"]);
});

test("shell scope recognizes extensionless hooks without including Python or excluded paths", (t) => {
  const root = fixture(t, {
    ".hooks/check": "#!/usr/bin/env bash\ntrue\n",
    "script.sh": "true\n",
    "script.py": "#!/usr/bin/env python3\n",
    "vendor/run": "#!/bin/sh\n",
  });
  assert.deepEqual(selectFiles(root, ":(glob)**/*\n:(exclude)vendor/**", true), [
    "./.hooks/check",
    "./script.sh",
  ]);
});

test("filenames containing whitespace, newlines, and shell syntax remain literal", (t) => {
  const names = ["a b.md", "line\nbreak.md", "$(touch injected).md", "-flag.md", "[literal].md"];
  const root = fixture(t, Object.fromEntries(names.map((name) => [name, "# Text\n"])));
  assert.deepEqual(new Set(selectFiles(root, "*.md")), new Set(names.map((name) => `./${name}`)));
  assert.equal(fs.existsSync(path.join(root, "injected")), false);
});

test("empty scopes skip while an empty selector is an error", (t) => {
  const root = fixture(t, { "README.md": "# Docs\n" });
  assert.deepEqual(selectFiles(root, "*.yaml"), []);
  assert.throws(() => selectFiles(root, " \n"), /pathspec/);
});

test("exclusions outside a fixed directory scope do not suppress its files", (t) => {
  const root = fixture(t, {
    ".github/workflows/ci.yaml": "",
    "vendor/other.yaml": "",
    "docs/notes.md": "",
  });
  assert.deepEqual(
    selectFiles(
      root,
      ".github/workflows/*.yaml\n:(glob,exclude)**/vendor/**\n:(exclude).mise/locks/**",
    ),
    ["./.github/workflows/ci.yaml"],
  );
});

test("the action emits a NUL list and the Common source directory", (t) => {
  const root = fixture(t, { "a b.md": "# Docs\n" });
  const output = path.join(root, "output");
  const result = spawnSync(process.execPath, [action], {
    cwd: root,
    encoding: "utf8",
    env: { ...process.env, INPUT_FILES: "*.md", GITHUB_OUTPUT: output, RUNNER_TEMP: root },
  });
  assert.equal(result.status, 0, result.stderr);
  const outputs = Object.fromEntries(
    fs
      .readFileSync(output, "utf8")
      .trim()
      .split("\n")
      .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]),
  );
  assert.equal(outputs.any, "true");
  assert.equal(fs.readFileSync(outputs["file-list"], "utf8"), "./a b.md\0");
  assert.equal(fs.existsSync(path.join(outputs["common-directory"], ".mise/mise.lock")), true);
});
