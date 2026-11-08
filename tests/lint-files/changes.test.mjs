import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { planLint } from "../../.github/actions/lint-files/index.mjs";

const action = fileURLToPath(new URL("../../.github/actions/lint-files/index.mjs", import.meta.url));
const git = (cwd, ...args) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
const defaults = {
  "README.md": "# Readme\n",
  "docs/guide.md": "# Guide\n",
  "app.yaml": "name: app\n",
  "app.go": "package main\n",
  "script.sh": "#!/bin/sh\ntrue\n",
  ".github/workflows/ci.yaml": "name: CI\n",
};
function write(root, files) {
  for (const [name, content] of Object.entries(files)) {
    if (content === null) fs.unlinkSync(path.join(root, name));
    else {
      fs.mkdirSync(path.dirname(path.join(root, name)), { recursive: true });
      fs.writeFileSync(path.join(root, name), content);
    }
  }
}
function commit(root, files = {}) {
  write(root, files);
  git(root, "add", "-A");
  git(root, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "--allow-empty", "-qm", "fixture");
  return git(root, "rev-parse", "HEAD");
}
function fixture(t, files = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lint-changes-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  git(root, "init", "-q", "-b", "main");
  const base = commit(root, { ...defaults, ...files });
  return { root, base };
}
function push(root, base, head, options = {}) {
  return planLint({ cwd: root, linter: "markdownlint", eventName: "push", event: { before: base, after: head, ref: "refs/heads/main" }, ...options });
}

test("unrelated pushes skip each linter despite existing matching files", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { "app.go": "package changed\n" });
  for (const linter of ["yamllint", "markdownlint", "shellcheck", "actionlint", "zizmor"]) {
    assert.deepEqual(push(root, base, head, { linter }), { files: [], reason: "unrelated-changes" });
  }
});

test("an affected scope includes unchanged peers and the entire multi-commit push", (t) => {
  const { root, base } = fixture(t);
  commit(root, { "README.md": "bad markdown\n" });
  const head = commit(root, { "app.go": "package changed\n" });
  assert.deepEqual(push(root, base, head), { files: ["./README.md", "./docs/guide.md"], reason: "scope-changed" });
});

test("PRs use the merge base and retain earlier changes after unrelated follow-up commits", (t) => {
  const { root, base } = fixture(t);
  git(root, "checkout", "-qb", "topic");
  commit(root, { "README.md": "bad markdown\n" });
  const head = commit(root, { "app.go": "package changed\n" });
  git(root, "checkout", "-q", "main");
  const updatedBase = commit(root, { "app.yaml": "name: updated\n" });
  git(root, "checkout", "-q", "topic");
  const event = { pull_request: { base: { sha: updatedBase }, head: { sha: head, repo: { full_name: "outside/fork" } } } };
  const options = { cwd: root, eventName: "pull_request", event };
  assert.equal(planLint({ ...options, linter: "markdownlint" }).reason, "scope-changed");
  assert.deepEqual(planLint({ ...options, linter: "yamllint" }).files, []);
  assert.notEqual(base, updatedBase);
});

test("merge groups compare the payload base and combined head", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { "app.yaml": "name: changed\n" });
  const options = { cwd: root, eventName: "merge_group", event: { merge_group: { base_sha: base, head_sha: head } } };
  assert.equal(planLint({ ...options, linter: "yamllint" }).reason, "scope-changed");
  assert.deepEqual(planLint({ ...options, linter: "markdownlint" }).files, []);
});

test("nested config modifications, renames, and deletions invalidate the Markdown scope", (t) => {
  const { root, base } = fixture(t, { "docs/.markdownlint.json": "{}\n" });
  let head = commit(root, { "docs/.markdownlint.json": "{\"default\":true}\n" });
  assert.equal(push(root, base, head).reason, "dependencies-changed");
  git(root, "mv", "docs/.markdownlint.json", "docs/old-config.json");
  head = commit(root);
  assert.equal(push(root, base, head).reason, "dependencies-changed");
});

test("custom config paths are literal and deletion still selects the entire scope", (t) => {
  const { root, base } = fixture(t, { "lint/[rules].json": "{}\n" });
  const head = commit(root, { "lint/[rules].json": null });
  assert.deepEqual(push(root, base, head).files, []);
  const result = push(root, base, head, { config: "lint/[rules].json" });
  assert.equal(result.reason, "dependencies-changed");
  assert.equal(result.files.length, 2);
});

test("caller workflow SHA updates, action locks, helper edits, and tool pins reselect every scope", (t) => {
  const { root, base } = fixture(t);
  for (const file of [".github/workflows/ci.yaml", ".github/workflows/actions.lock", ".github/actions/custom/index.mjs", ".mise/mise.lock"]) {
    const head = commit(root, { [file]: "changed\n" });
    for (const linter of ["yamllint", "markdownlint", "shellcheck", "actionlint", "zizmor"])
      assert.equal(push(root, base, head, { linter }).reason, "dependencies-changed");
    git(root, "reset", "--hard", base);
  }
});

test("additional dependency paths trigger checks outside the lint file scope", (t) => {
  const { root, base } = fixture(t, { "rules/custom.mjs": "export default {};\n" });
  const head = commit(root, { "rules/custom.mjs": "export default {changed:true};\n" });
  assert.deepEqual(push(root, base, head).files, []);
  assert.equal(push(root, base, head, { triggerFiles: "rules/**" }).reason, "dependencies-changed");
});

test("extra trigger exclusions cannot suppress built-in workflow or config dependencies", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { ".github/workflows/ci.yaml": "name: Updated\n" });
  assert.equal(push(root, base, head, { triggerFiles: "rules/**\n:(exclude).github/**" }).reason, "dependencies-changed");
});

test("excluded Markdown changes skip and scope overrides keep their own boundaries", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { "vendor/readme.md": "# Vendor\n", "CHANGELOG.md": "# Release\n" });
  assert.deepEqual(push(root, base, head).files, []);
  const second = commit(root, { "README.md": "# Updated\n" });
  assert.deepEqual(push(root, head, second, { files: "docs/**/*.md" }).files, []);
});

test("renaming a file out of a scope rechecks remaining files; empty scopes still skip", (t) => {
  const { root, base } = fixture(t);
  git(root, "mv", "docs/guide.md", "docs/guide.txt");
  let head = commit(root);
  assert.deepEqual(push(root, base, head).files, ["./README.md"]);
  head = commit(root, { "README.md": null });
  assert.equal(push(root, base, head).reason, "no-files");
});

test("shell selection notices deleted extensionless sources but ignores new non-shell files", (t) => {
  const { root, base } = fixture(t, { ".hooks/source": "#!/usr/bin/env bash\ntrue\n" });
  const docs = commit(root, { "docs/new.md": "# New\n" });
  assert.deepEqual(push(root, base, docs, { linter: "shellcheck" }).files, []);
  const head = commit(root, { ".hooks/source": null });
  assert.deepEqual(push(root, docs, head, { linter: "shellcheck" }).files, ["./script.sh"]);
});

test("manual, scheduled, new branch, tag, and unsupported events conservatively scan", (t) => {
  const { root, base } = fixture(t);
  for (const [eventName, event] of [
    ["workflow_dispatch", {}], ["schedule", {}], ["release", {}],
    ["push", { created: true, before: base, after: base }],
    ["push", { ref: "refs/tags/v0.1.0", before: base, after: base }],
  ]) assert.equal(planLint({ cwd: root, linter: "markdownlint", eventName, event }).files.length, 2);
  assert.equal(push(root, base, base).files.length, 0);
  assert.equal(push(root, base, base, { fullScan: true }).files.length, 2);
});

test("missing history, zero SHAs, and injection-like event refs never authorize skipping", (t) => {
  const { root, base } = fixture(t);
  for (const before of ["0".repeat(40), "a".repeat(40), "--output=owned", "$(touch owned)", "HEAD~1"]) {
    const result = push(root, before, base);
    assert.equal(result.reason, "history-unavailable");
    assert.equal(result.files.length, 2);
  }
  assert.equal(fs.existsSync(path.join(root, "owned")), false);
});

test("a real shallow checkout falls back to scanning instead of skipping", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { "app.go": "package changed\n" });
  const clone = `${root}-shallow`;
  t.after(() => fs.rmSync(clone, { recursive: true, force: true }));
  git(root, "clone", "-q", "--depth=1", `file://${root}`, clone);
  assert.equal(push(clone, base, head).reason, "history-unavailable");
});

test("untrusted changes cannot switch linting to privileged event contexts", (t) => {
  const { root } = fixture(t);
  for (const eventName of ["pull_request_target", "workflow_run"])
    assert.throws(() => planLint({ cwd: root, linter: "markdownlint", eventName, fullScan: true }), /unprivileged/);
  assert.throws(() => planLint({ cwd: root, linter: "__proto__" }), /Unknown linter/);
  for (const config of ["/tmp/config.yaml", "../config.yaml"])
    assert.throws(() => planLint({ cwd: root, linter: "markdownlint", config, fullScan: true }), /repository-relative/);
});

test("large changesets and special filenames are not truncated or shell-evaluated", (t) => {
  const { root, base } = fixture(t);
  const special = "z/$(touch owned) [x]\n.md";
  const files = Object.fromEntries(Array.from({ length: 3100 }, (_, i) => [`a/${i}.txt`, "data\n"]));
  files[special] = "# Changed\n";
  const head = commit(root, files);
  const result = push(root, base, head);
  assert.equal(result.reason, "scope-changed");
  assert.ok(result.files.includes(`./${special}`));
  assert.equal(fs.existsSync(path.join(root, "owned")), false);
});

test("the action emits false and an empty list for an unrelated real event", (t) => {
  const { root, base } = fixture(t);
  const head = commit(root, { "app.go": "package changed\n" });
  const eventPath = path.join(root, "event.json");
  const output = path.join(root, "output");
  fs.writeFileSync(eventPath, JSON.stringify({ before: base, after: head, ref: "refs/heads/main" }));
  const result = spawnSync(process.execPath, [action], {
    cwd: root, encoding: "utf8",
    env: { ...process.env, INPUT_LINTER: "markdownlint", INPUT_FILES: "", GITHUB_EVENT_NAME: "push", GITHUB_EVENT_PATH: eventPath, GITHUB_OUTPUT: output, RUNNER_TEMP: root },
  });
  assert.equal(result.status, 0, result.stderr);
  const values = Object.fromEntries(fs.readFileSync(output, "utf8").trim().split("\n").map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1)]));
  assert.equal(values.any, "false");
  assert.equal(values.reason, "unrelated-changes");
  assert.equal(fs.readFileSync(values["file-list"], "utf8"), "");
});
