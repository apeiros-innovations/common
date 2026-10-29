import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { retry, retryCompleted } from "../../.github/actions/retry-renovate-check/index.mjs";

const repository = "apeiros-innovations/example";
const sha = "a".repeat(40);
const login = "autoforgex[bot]";
const event = { sha, state: "success", context: "renovate/artifacts", sender: { login } };
const pr = {
  number: 7,
  state: "open",
  user: { login, type: "Bot" },
  head: { sha, ref: "renovate/tools", repo: { full_name: repository } },
  base: { repo: { full_name: repository } },
};
const run = {
  id: 99,
  head_sha: sha,
  head_branch: pr.head.ref,
  event: "pull_request",
  pull_requests: [{ number: 7 }],
  status: "completed",
  conclusion: "failure",
  run_attempt: 1,
};
const jobs = [
  { id: 100, name: "Validate", conclusion: "success" },
  { id: 101, name: "Build Success", conclusion: "failure" },
];
const green = [{ context: "renovate/artifacts", state: "success", creator: { login } }];

test("the action entrypoint executes a safe no-op and rejects unsupported events", (t) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "renovate-check-retry-"));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const eventPath = path.join(directory, "event.json");
  fs.writeFileSync(eventPath, JSON.stringify({ ...event, state: "pending" }));
  for (const action of ["retry-renovate-check"]) {
    const entrypoint = fileURLToPath(
      new URL(`../../.github/actions/${action}/index.mjs`, import.meta.url),
    );
    const env = {
      ...process.env,
      GITHUB_EVENT_PATH: eventPath,
      GITHUB_EVENT_NAME: "status",
      GITHUB_REPOSITORY: repository,
      GITHUB_API_URL: "https://api.github.com",
      "INPUT_GITHUB-TOKEN": "fixture-token",
    };
    const result = spawnSync(process.execPath, [entrypoint], { env, encoding: "utf8" });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /Retried 0 required CI check job\(s\)/);
    const rejected = spawnSync(process.execPath, [entrypoint], {
      env: { ...env, GITHUB_EVENT_NAME: "pull_request" },
      encoding: "utf8",
    });
    assert.equal(rejected.status, 1);
    assert.match(rejected.stdout, /only accepts status and workflow_run/);
  }
});

function fixture({
  prs = [pr],
  runs = [run],
  jobList = jobs,
  statuses = green,
  current = pr,
} = {}) {
  const writes = [];
  const client = {
    async pages(route) {
      if (route.endsWith("/pulls")) return structuredClone(prs);
      if (route.endsWith("/statuses")) return structuredClone(statuses);
      if (route.includes("/actions/workflows/ci.yaml/runs?")) return structuredClone(runs);
      if (route.includes("/actions/runs/99/jobs?")) return structuredClone(jobList);
      throw new Error(`Unexpected read ${route}`);
    },
    async request(route, method = "GET") {
      if (method === "POST") {
        writes.push(route);
        return;
      }
      assert.equal(route, "/pulls/7");
      return structuredClone(current);
    },
  };
  return { client, writes };
}

test("only the final blocked job is retried; dependency PRs are never merged", async () => {
  const { client, writes } = fixture();
  assert.deepEqual(await retry({ event, client, repository }), [101]);
  assert.deepEqual(writes, ["/actions/jobs/101/rerun"]);
});

test("unrelated events, publishers and old PR heads do not write", async () => {
  for (const changed of [
    { ...event, state: "pending" },
    { ...event, context: "other/context" },
    { ...event, sender: { login: "human" } },
  ]) {
    const { client, writes } = fixture();
    assert.deepEqual(await retry({ event: changed, client, repository }), []);
    assert.deepEqual(writes, []);
  }
  for (const options of [
    { prs: [] },
    { prs: [{ ...pr, state: "closed" }] },
    { prs: [{ ...pr, head: { ...pr.head, sha: "b".repeat(40) } }] },
    { current: { ...pr, state: "closed" } },
    { current: { ...pr, head: { ...pr.head, sha: "b".repeat(40) } } },
  ]) {
    const { client, writes } = fixture(options);
    assert.deepEqual(await retry({ event, client, repository }), []);
    assert.deepEqual(writes, []);
  }
});

test("failed or missing artifacts and pending release-age holds remain blocking", async () => {
  for (const statuses of [
    [],
    [{ ...green[0], state: "failure" }],
    [...green, { context: "renovate/stability-days", state: "pending", creator: { login } }],
  ]) {
    const { client, writes } = fixture({ statuses });
    assert.deepEqual(await retry({ event, client, repository }), []);
    assert.deepEqual(writes, []);
  }
});

test("failed upstream work, in-flight runs, obsolete runs and rerun limits do not retry", async () => {
  for (const options of [
    { jobList: [{ ...jobs[0], conclusion: "failure" }, jobs[1]] },
    { jobList: [{ ...jobs[0], conclusion: "cancelled" }, jobs[1]] },
    { jobList: [jobs[0], { ...jobs[1], conclusion: "success" }] },
    { jobList: [jobs[0]] },
    { runs: [{ ...run, status: "in_progress" }] },
    { runs: [{ ...run, pull_requests: [{ number: 8 }] }] },
    { runs: [{ ...run, head_branch: "unrelated" }] },
    { runs: [{ ...run, run_attempt: 45 }] },
    { runs: [run, { ...run, id: 101, conclusion: "success" }] },
  ]) {
    const { client, writes } = fixture(options);
    assert.deepEqual(await retry({ event, client, repository }), []);
    assert.deepEqual(writes, []);
  }
});

test("API failures propagate instead of publishing a successful gate", async () => {
  const { client } = fixture();
  client.pages = async () => {
    throw new Error("GitHub unavailable");
  };
  await assert.rejects(() => retry({ event, client, repository }), /unavailable/);
});

test("completion closes the status race once and cannot retry a newer run", async () => {
  const { client, writes } = fixture();
  assert.deepEqual(
    await retryCompleted({ event: { workflow_run: run }, client, repository }),
    [101],
  );
  assert.deepEqual(writes, ["/actions/jobs/101/rerun"]);
  for (const changed of [
    { ...run, run_attempt: 2 },
    { ...run, conclusion: "success" },
    { ...run, event: "push" },
    { ...run, id: 98 },
    { ...run, head_sha: "untrusted" },
    { ...run, pull_requests: [] },
  ]) {
    const f = fixture();
    assert.deepEqual(
      await retryCompleted({ event: { workflow_run: changed }, client: f.client, repository }),
      [],
    );
    assert.deepEqual(f.writes, []);
  }
  const blocked = fixture({ statuses: [] });
  assert.deepEqual(
    await retryCompleted({ event: { workflow_run: run }, client: blocked.client, repository }),
    [],
  );
  assert.deepEqual(blocked.writes, []);
});
