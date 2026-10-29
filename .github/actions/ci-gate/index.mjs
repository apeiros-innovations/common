import { fileURLToPath } from "node:url";
import path from "node:path";
import { fail, githubClient, isRenovatePr, readEvent, renovateReadiness } from "./github.mjs";

const object = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
const jobId = /^[A-Za-z_][A-Za-z0-9_-]*$/;

export function assessNeeds(needs, expected) {
  if (!object(needs) || !object(expected) || Object.keys(needs).length === 0)
    throw new Error("needs and expected must be nonempty JSON objects");
  const keys = [...new Set([...Object.keys(needs), ...Object.keys(expected)])].sort();
  const errors = [];
  for (const key of keys) {
    if (!jobId.test(key)) throw new Error("Invalid job ID in CI gate input");
    if (!Object.hasOwn(needs, key)) {
      errors.push(`${key}: missing dependency result`);
      continue;
    }
    if (!Object.hasOwn(expected, key)) {
      errors.push(`${key}: missing selection decision`);
      continue;
    }
    const selected = expected[key];
    if (![true, false, "true", "false"].includes(selected)) {
      errors.push(`${key}: selection must be true or false`);
      continue;
    }
    const result = needs[key]?.result;
    const wanted = selected === true || selected === "true" ? "success" : "skipped";
    if (!object(needs[key]) || result !== wanted) errors.push(`${key}: expected ${wanted}`);
  }
  return errors;
}

function jsonInput(name) {
  try {
    return JSON.parse(process.env[`INPUT_${name.toUpperCase()}`]);
  } catch {
    throw new Error(`Invalid JSON in ${name} input`);
  }
}

export async function run() {
  // https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#needs-context
  const errors = assessNeeds(jsonInput("needs"), jsonInput("expected"));
  if (errors.length) throw new Error(errors.join("; "));
  const readiness = process.env["INPUT_RENOVATE-READINESS"] ?? "true";
  if (!["true", "false"].includes(readiness))
    throw new Error("renovate-readiness must be true or false");
  if (readiness === "true" && process.env.GITHUB_EVENT_NAME === "pull_request") {
    const event = readEvent();
    const pr = event.pull_request;
    if (isRenovatePr(pr, process.env.GITHUB_REPOSITORY)) {
      const client = githubClient({
        repository: process.env.GITHUB_REPOSITORY,
        token: process.env["INPUT_GITHUB-TOKEN"],
        apiUrl: process.env.GITHUB_API_URL,
      });
      errors.push(...(await renovateReadiness(client, pr.head.sha, pr.user.login)));
    }
  }
  if (errors.length) throw new Error(errors.join("; "));
  process.stdout.write("All selected checks passed.\n");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  await run().catch(fail);