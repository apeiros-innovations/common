import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

// A missing remote can leave Lefthook with an incomplete but valid config.
// Verify loaded checks before running; file globs still decide applicability.
export function checkConfig(config, expected) {
  if (
    !Array.isArray(expected) ||
    expected.length === 0 ||
    expected.some((name) => typeof name !== "string" || !name.trim())
  ) {
    throw new Error("expected-checks must be a nonempty JSON array of job names");
  }
  const hook = config["pre-commit"];
  if (!hook || hook.skip === true) {
    throw new Error("pre-commit must be enabled");
  }
  const enabled = new Set();
  function visit(jobs) {
    for (const job of jobs ?? []) {
      if (job.skip === true) continue;
      if (job.group) visit(job.group.jobs);
      else if (job.tags?.includes("ci") && (job.run || job.script)) enabled.add(job.name);
    }
  }
  visit(hook.jobs);
  const missing = expected.filter((name) => !enabled.has(name));
  if (missing.length) {
    throw new Error(
      `Required checks are missing, disabled, or lack the ci tag: ${missing.join(", ")}`,
    );
  }
  return [...enabled].sort();
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const config = JSON.parse(readFileSync(process.argv[2], "utf8"));
    const checks = checkConfig(config, JSON.parse(process.env.LINT_EXPECTED_CHECKS));
    console.log(`Loaded CI checks: ${checks.join(", ")}`);
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
