import fs from "node:fs";

export const renovateLogins = new Set(["autoforgex[bot]", "renovate[bot]"]);
export const artifactContext = "renovate/artifacts";
export const readinessContexts = new Set([
  artifactContext,
  "renovate/stability-days",
  "renovate/merge-confidence",
  "renovate/config-validation",
]);

export function isRenovatePr(pr, repository) {
  return (
    pr?.user?.type === "Bot" &&
    renovateLogins.has(pr.user.login) &&
    pr.head?.ref?.startsWith("renovate/") &&
    pr.head.repo?.full_name === repository &&
    pr.base?.repo?.full_name === repository
  );
}

export function readEvent() {
  if (!process.env.GITHUB_EVENT_PATH) throw new Error("GITHUB_EVENT_PATH is required");
  return JSON.parse(fs.readFileSync(process.env.GITHUB_EVENT_PATH, "utf8"));
}

export function githubClient({
  repository,
  token,
  apiUrl = "https://api.github.com",
  fetchImpl = fetch,
}) {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository ?? ""))
    throw new Error("Invalid repository");
  if (!token) throw new Error("A GitHub token is required to read Renovate readiness");
  // This rollout targets GitHub.com; do not forward credentials to a caller URL.
  if (apiUrl !== "https://api.github.com") throw new Error("Unsupported GitHub API origin");
  const request = async (suffix, method = "GET") => {
    if (!suffix.startsWith("/") || suffix.includes("..")) throw new Error("Invalid API path");
    const response = await fetchImpl(`${apiUrl}/repos/${repository}${suffix}`, {
      method,
      redirect: "error",
      signal: AbortSignal.timeout(15000),
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${token}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
    });
    // Error bodies and job outputs can contain private data. Report only status.
    if (!response.ok) throw new Error(`GitHub ${method} request failed (${response.status})`);
    return response.status === 204 || (response.status === 201 && method === "POST")
      ? undefined
      : response.json();
  };
  const pages = async (suffix, key) => {
    const items = [];
    for (let page = 1; page <= 20; page++) {
      const data = await request(
        `${suffix}${suffix.includes("?") ? "&" : "?"}per_page=100&page=${page}`,
      );
      const batch = key ? data[key] : data;
      if (!Array.isArray(batch)) throw new Error("Invalid GitHub collection response");
      items.push(...batch);
      if (batch.length < 100) return items;
    }
    throw new Error("GitHub collection exceeded the pagination limit");
  };
  return { request, pages };
}

export async function renovateReadiness(client, sha, login) {
  if (!/^[a-f0-9]{40}$/.test(sha ?? "")) throw new Error("Invalid pull request head SHA");
  const statuses = await client.pages(`/commits/${sha}/statuses`);
  // GitHub returns newest first. An older successful status cannot hide a failure.
  const latest = new Map();
  for (const status of statuses)
    if (readinessContexts.has(status.context) && !latest.has(status.context))
      latest.set(status.context, status);
  const errors = [];
  if (!latest.has(artifactContext)) errors.push("Renovate artifact status has not been reported");
  for (const [context, status] of latest) {
    if (status.creator?.login !== login) errors.push(`${context}: unexpected status publisher`);
    else if (status.state !== "success") errors.push(`${context}: not successful`);
  }
  return errors;
}

export function fail(error) {
  const escaped = String(error.message)
    .replaceAll("%", "%25")
    .replaceAll("\r", "%0D")
    .replaceAll("\n", "%0A");
  process.stdout.write(`::error::${escaped}\n`);
  process.exitCode = 1;
}