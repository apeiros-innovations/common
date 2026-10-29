import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { assessNeeds } from "../../.github/actions/ci-gate/index.mjs";
import {
  githubClient,
  isRenovatePr,
  renovateReadiness,
} from "../../.github/actions/ci-gate/github.mjs";

const repository = "apeiros-innovations/example";
const sha = "a".repeat(40);
const login = "autoforgex[bot]";
const status = (context = "renovate/artifacts", state = "success", creator = login) => ({
  context,
  state,
  creator: { login: creator },
});

test("selected jobs must succeed and explicitly unselected jobs must skip", () => {
  assert.deepEqual(
    assessNeeds(
      { select: { result: "success" }, build: { result: "success" }, docs: { result: "skipped" } },
      { select: true, build: "true", docs: "false" },
    ),
    [],
  );
  for (const result of ["failure", "cancelled", "skipped", "neutral", "pending", undefined]) {
    assert.ok(assessNeeds({ build: { result } }, { build: true }).length, result);
  }
  assert.ok(assessNeeds({ docs: { result: "success" } }, { docs: false }).length);
});

test("missing dependencies and missing or invalid selection decisions fail closed", () => {
  assert.ok(
    assessNeeds({ select: { result: "success" } }, { select: true, build: true }).some((s) =>
      s.includes("build: missing"),
    ),
  );
  assert.ok(
    assessNeeds(
      { select: { result: "success" }, added: { result: "success" } },
      { select: true },
    ).some((s) => s.includes("added: missing")),
  );
  for (const selected of ["", "yes", 1, null, [], {}])
    assert.ok(assessNeeds({ build: { result: "success" } }, { build: selected }).length);
  for (const input of [null, [], {}, "success"]) assert.throws(() => assessNeeds(input, {}));
  assert.throws(() => assessNeeds({ "bad\n::error::job": {} }, {}));
});

test("private job outputs are ignored and are never included in errors", () => {
  const result = assessNeeds(
    { build: { result: "failure", outputs: { credential: "private-marker" } } },
    { build: true },
  );
  assert.ok(!JSON.stringify(result).includes("private-marker"));
});

test("Renovate recognition excludes release PRs, humans, forks and other bots", () => {
  const pr = {
    user: { login, type: "Bot" },
    head: { sha, ref: "renovate/tools", repo: { full_name: repository } },
    base: { repo: { full_name: repository } },
  };
  assert.equal(isRenovatePr(pr, repository), true);
  for (const changed of [
    { ...pr, user: { login, type: "User" } },
    { ...pr, user: { login: "other[bot]", type: "Bot" } },
    { ...pr, head: { ...pr.head, ref: "release-please/main" } },
    { ...pr, head: { ...pr.head, repo: { full_name: "fork/example" } } },
  ])
    assert.equal(isRenovatePr(changed, repository), false);
});

test("missing metadata is allowed; reported failures and pending holds block readiness", async () => {
  const client = (statuses) => ({ pages: async () => statuses });
  assert.deepEqual(await renovateReadiness(client([status()]), sha, login), []);
  assert.deepEqual(await renovateReadiness(client([]), sha, login), []);
  for (const context of [
    "renovate/artifacts",
    "renovate/stability-days",
    "renovate/merge-confidence",
    "renovate/config-validation",
  ]) {
    assert.ok((await renovateReadiness(client([status(context, "pending")]), sha, login)).length);
    assert.ok((await renovateReadiness(client([status(context, "failure")]), sha, login)).length);
  }
  assert.ok(
    (
      await renovateReadiness(
        client([status("renovate/artifacts", "failure"), status()]),
        sha,
        login,
      )
    ).length,
  );
  assert.ok(
    (
      await renovateReadiness(
        client([status(), status("renovate/stability-days", "pending")]),
        sha,
        login,
      )
    ).length,
  );
  assert.ok(
    (
      await renovateReadiness(
        client([status("renovate/artifacts", "success", "another-user")]),
        sha,
        login,
      )
    ).length,
  );
  assert.deepEqual(
    await renovateReadiness(client([status(), status("renovate/stability-days")]), sha, login),
    [],
  );
  await assert.rejects(() => renovateReadiness(client([]), "../main", login));
});

test("GitHub client paginates, bounds requests and never follows credential redirects", async () => {
  const calls = [];
  const client = githubClient({
    repository,
    token: "test-token",
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return {
        ok: true,
        status: 200,
        json: async () =>
          calls.length === 1 ? Array.from({ length: 100 }, (_, id) => ({ id })) : [{ id: 101 }],
      };
    },
  });
  assert.equal((await client.pages(`/commits/${sha}/statuses`)).length, 101);
  assert.ok(calls[1].url.endsWith("per_page=100&page=2"));
  assert.equal(calls[0].options.redirect, "error");
  assert.equal(calls[0].options.headers.Authorization, "Bearer test-token");
  assert.ok(calls[0].options.signal instanceof AbortSignal);
  assert.throws(() =>
    githubClient({ repository, token: "test-token", apiUrl: "https://untrusted.invalid" }),
  );
  assert.throws(() => githubClient({ repository: "owner/../else", token: "test-token" }));
  const failed = githubClient({
    repository,
    token: "test-token",
    fetchImpl: async () => ({
      ok: false,
      status: 403,
      text: () => {
        throw Error("private response");
      },
    }),
  });
  await assert.rejects(() => failed.request("/pulls/1"), /403/);
});

test("the action executable handles ordinary PRs, malformed input and skipped jobs", () => {
  const script = fileURLToPath(new URL("../../.github/actions/ci-gate/index.mjs", import.meta.url));
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "ci-gate-"));
  const event = path.join(directory, "event.json");
  fs.writeFileSync(
    event,
    JSON.stringify({ pull_request: { user: { type: "User", login: "contributor" } } }),
  );
  const env = {
    ...process.env,
    GITHUB_EVENT_NAME: "pull_request",
    GITHUB_EVENT_PATH: event,
    GITHUB_REPOSITORY: repository,
    INPUT_NEEDS: '{"build":{"result":"success"}}',
    INPUT_EXPECTED: '{"build":true}',
  };
  try {
    assert.match(
      execFileSync(process.execPath, [script], { env, encoding: "utf8" }),
      /All selected checks passed/,
    );
    const skipped = spawnSync(process.execPath, [script], {
      env: { ...env, INPUT_NEEDS: '{"build":{"result":"skipped"}}' },
      encoding: "utf8",
    });
    assert.equal(skipped.status, 1);
    const malformed = spawnSync(process.execPath, [script], {
      env: { ...env, INPUT_NEEDS: "private-marker invalid json" },
      encoding: "utf8",
    });
    assert.equal(malformed.status, 1);
    assert.ok(!`${malformed.stdout}${malformed.stderr}`.includes("private-marker"));
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
