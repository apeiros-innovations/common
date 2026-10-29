import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  fail,
  githubClient,
  isRenovatePr,
  readEvent,
  readinessContexts,
  renovateLogins,
  renovateReadiness,
} from "../ci-gate/github.mjs";

export async function retry({ event, client, repository, workflow = "ci.yaml", completedRunId }) {
  if (!/^[a-zA-Z0-9_-]+\.ya?ml$/.test(workflow)) throw new Error("Invalid workflow filename");
  if (
    event.state !== "success" ||
    !readinessContexts.has(event.context) ||
    !renovateLogins.has(event.sender?.login)
  )
    return [];
  if (!/^[a-f0-9]{40}$/.test(event.sha ?? "")) throw new Error("Invalid status SHA");
  const prs = await client.pages(`/commits/${event.sha}/pulls`);
  const matching = prs.filter(
    (pr) =>
      pr.state === "open" &&
      pr.head.sha === event.sha &&
      isRenovatePr(pr, repository) &&
      pr.user.login === event.sender.login,
  );
  if (
    matching.length === 0 ||
    (await renovateReadiness(client, event.sha, event.sender.login)).length > 0
  )
    return [];
  const runs = await client.pages(
    `/actions/workflows/${workflow}/runs?event=pull_request&head_sha=${event.sha}`,
    "workflow_runs",
  );
  const retried = [];
  for (const pr of matching) {
    // Never retry an old attempt or a workflow from a different PR/branch.
    const run = runs
      .filter(
        (r) =>
          r.head_sha === event.sha &&
          r.head_branch === pr.head.ref &&
          r.pull_requests?.some((p) => p.number === pr.number),
      )
      .sort((a, b) => b.id - a.id)[0];
    if (
      !run ||
      (completedRunId !== undefined && run.id !== completedRunId) ||
      run.status !== "completed" ||
      run.conclusion !== "failure" ||
      run.run_attempt >= 45
    )
      continue;
    const jobs = await client.pages(`/actions/runs/${run.id}/jobs?filter=latest`, "jobs");
    const gates = jobs.filter((job) => job.name === "Build Success");
    if (gates.length !== 1 || gates[0].conclusion !== "failure") continue;
    if (
      jobs.some((job) => job.id !== gates[0].id && !["success", "skipped"].includes(job.conclusion))
    )
      continue;
    // Re-fetch immediately before the write: a pushed or closed PR is obsolete.
    const current = await client.request(`/pulls/${pr.number}`);
    if (
      current.state !== "open" ||
      current.head.sha !== event.sha ||
      !isRenovatePr(current, repository)
    )
      continue;
    if ((await renovateReadiness(client, event.sha, current.user.login)).length > 0) continue;
    // https://docs.github.com/en/rest/actions/workflow-runs#re-run-a-job-from-a-workflow-run
    await client.request(`/actions/jobs/${gates[0].id}/rerun`, "POST");
    retried.push(gates[0].id);
  }
  return retried;
}

export async function retryCompleted({ event, client, repository, workflow }) {
  const run = event.workflow_run;
  // Close the status/completion race once. Subsequent attempts wait for a new
  // Renovate status rather than repeatedly retrying an unrelated gate failure.
  if (
    run?.event !== "pull_request" ||
    run.conclusion !== "failure" ||
    run.run_attempt !== 1 ||
    !Number.isSafeInteger(run.id) ||
    !/^[a-f0-9]{40}$/.test(run.head_sha ?? "")
  )
    return [];
  const prs = await client.pages(`/commits/${run.head_sha}/pulls`);
  const pr = prs.find(
    (p) =>
      p.state === "open" &&
      p.head.sha === run.head_sha &&
      run.pull_requests?.some((r) => r.number === p.number) &&
      isRenovatePr(p, repository),
  );
  if (!pr) return [];
  return retry({
    event: {
      sha: run.head_sha,
      state: "success",
      context: "renovate/artifacts",
      sender: { login: pr.user.login },
    },
    client,
    repository,
    workflow,
    completedRunId: run.id,
  });
}

export async function run() {
  if (!["status", "workflow_run"].includes(process.env.GITHUB_EVENT_NAME))
    throw new Error("Retry Renovate check only accepts status and workflow_run events");
  const repository = process.env.GITHUB_REPOSITORY;
  const client = githubClient({
    repository,
    token: process.env["INPUT_GITHUB-TOKEN"],
    apiUrl: process.env.GITHUB_API_URL,
  });
  const handler = process.env.GITHUB_EVENT_NAME === "workflow_run" ? retryCompleted : retry;
  const jobs = await handler({
    event: readEvent(),
    repository,
    client,
    workflow: process.env.INPUT_WORKFLOW || "ci.yaml",
  });
  process.stdout.write(`Retried ${jobs.length} required CI check job(s).\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  await run().catch(fail);
