import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

function fixture(t, jobs) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "common-lint-"));
  t.after(() => fs.rmSync(cwd, { recursive: true, force: true }));
  const env = { ...process.env, CI: "true", LEFTHOOK_CONFIG: path.join(cwd, ".lefthook.yml") };
  const run = (command, args) => spawnSync(command, args, { cwd, env, encoding: "utf8" });
  function mustRun(command, args) {
    const result = run(command, args);
    assert.equal(result.status, 0, result.stderr || result.stdout || result.error?.message);
  }
  mustRun("git", ["init", "--quiet"]);
  fs.writeFileSync(env.LEFTHOOK_CONFIG, JSON.stringify({ "pre-commit": { jobs } }));
  fs.writeFileSync(path.join(cwd, "tracked.txt"), "original\n");
  mustRun("git", ["add", "."]);
  mustRun("git", [
    "-c",
    "user.name=Test",
    "-c",
    "user.email=test@example.invalid",
    "commit",
    "-qm",
    "fixture",
  ]);
  mustRun("lefthook", ["install"]);
  return {
    cwd,
    lint: () =>
      run("lefthook", [
        "run",
        "pre-commit",
        "--tag",
        "ci",
        "--all-files",
        "--no-stage-fixed",
        "--fail-on-changes",
        "--no-auto-install",
        "--no-tty",
      ]),
    run,
  };
}

test("CI checks run on committed files without a staged diff", (t) => {
  const f = fixture(t, [
    { name: "inspect", tags: ["ci"], glob: "*.txt", run: "test -s {staged_files}" },
  ]);
  const result = f.lint();
  assert.equal(result.status, 0, result.stderr + result.stdout);
  assert.match(result.stdout, /inspect/);
});

test("a failing selected linter fails the run", (t) => {
  const f = fixture(t, [{ name: "reject", tags: ["ci"], run: "exit 7" }]);
  assert.notEqual(f.lint().status, 0);
});

test("formatter edits fail CI without staging the changes", (t) => {
  const f = fixture(t, [
    {
      name: "format",
      tags: ["ci"],
      glob: "*.txt",
      stage_fixed: true,
      run: "printf 'changed\\n' > {staged_files}",
    },
  ]);
  assert.notEqual(f.lint().status, 0);
  assert.equal(fs.readFileSync(path.join(f.cwd, "tracked.txt"), "utf8"), "changed\n");
  assert.equal(f.run("git", ["diff", "--cached", "--exit-code"]).status, 0);
});

test("local-only generators are excluded from CI", (t) => {
  const f = fixture(t, [
    { name: "check", tags: ["ci"], run: "true" },
    { name: "generate", tags: ["generation"], run: "touch generated.txt; exit 7" },
  ]);
  assert.equal(f.lint().status, 0);
  assert.equal(fs.existsSync(path.join(f.cwd, "generated.txt")), false);
});
