import { execFileSync } from "node:child_process";
import {
  appendFileSync,
  closeSync,
  lstatSync,
  mkdtempSync,
  openSync,
  readFileSync,
  readSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const profiles = JSON.parse(readFileSync(new URL("./profiles.json", import.meta.url), "utf8"));
const sharedTriggers = [
  ".github/workflows/**", // Includes caller workflow SHA updates and actions.lock.
  ".github/actions/**",
  ".mise/**",
  "tests/lint-files/**",
];
const git = (cwd, args) => execFileSync("git", args, {
  cwd,
  encoding: "utf8",
  maxBuffer: 32 * 1024 * 1024,
  timeout: 20_000,
  stdio: ["ignore", "pipe", "pipe"],
});

function matchPaths(input, list) {
  const patterns = input
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (!patterns.length) throw new Error("files must contain at least one Git pathspec");
  const isExclusion = (pattern) => /^:(?:!|\^|\([^)]*\bexclude\b[^)]*\))/.test(pattern);
  const includes = patterns.filter((pattern) => !isExclusion(pattern));
  const excludes = patterns.filter(isExclusion);
  const tracked = list(includes.length ? includes : [":(top,glob)**"]);
  // Apply exclusions to the root inventory. Git 2.52 otherwise drops a fixed
  // directory scope when an exclusion lies outside that directory's prefix.
  const allowed = excludes.length ? new Set(list([":(top,glob)**", ...excludes])) : null;
  return [...new Set(tracked)].filter((file) => !allowed || allowed.has(file));
}

const shellExtension = (file) => /\.(?:sh|bash|bats|ksh)$/.test(file);
const shellShebang = (prefix) => /^#![^\r\n]*\b(?:sh|bash|dash|ksh|ash)\b/.test(prefix);

export function selectFiles(cwd, input, shellOnly = false) {
  // Git owns path matching; no shell expansion or evaluation of filenames.
  const tracked = matchPaths(input, (specs) =>
    git(cwd, ["ls-files", "-z", "--", ...specs]).split("\0").filter(Boolean));
  return tracked
    .filter((file) => {
      const absolute = path.join(cwd, file);
      try {
        if (!lstatSync(absolute).isFile()) return false;
      } catch (error) {
        if (error.code === "ENOENT") return false;
        throw error;
      }
      if (!shellOnly || shellExtension(file)) return true;
      const fd = openSync(absolute, "r");
      try {
        const buffer = Buffer.alloc(256);
        const bytes = readSync(fd, buffer, 0, buffer.length, 0);
        return shellShebang(buffer.subarray(0, bytes).toString());
      } finally {
        closeSync(fd);
      }
    })
    .map((file) => `./${file}`);
}

function comparison(cwd, eventName, event) {
  // GitHub documents PR three-dot and existing-branch push two-dot comparisons:
  // https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#git-diff-comparisons
  let base;
  let head;
  if (eventName === "pull_request") {
    base = event.pull_request?.base?.sha;
    head = event.pull_request?.head?.sha;
  } else if (eventName === "push" && !event.created && !event.ref?.startsWith("refs/tags/")) {
    base = event.before;
    head = event.after;
  } else if (eventName === "merge_group") {
    base = event.merge_group?.base_sha;
    head = event.merge_group?.head_sha;
  } else {
    return null;
  }
  // Never accept refs, flags, or expressions from event data as Git arguments.
  const sha = /^(?:[a-f0-9]{40}|[a-f0-9]{64})$/i;
  if (![base, head].every((value) => typeof value === "string" && sha.test(value) && !/^0+$/.test(value)))
    throw new Error("Missing comparison commits");
  for (const commit of [base, head]) git(cwd, ["rev-parse", "--verify", `${commit}^{commit}`]);
  if (eventName === "pull_request") base = git(cwd, ["merge-base", base, head]).trim();
  return { base, head };
}

export function planLint({
  cwd, linter = "", files = "", shellOnly = false, config = "", triggerFiles = "",
  fullScan = false, eventName = "", event = {},
}) {
  if (linter && !Object.hasOwn(profiles, linter)) throw new Error("Unknown linter profile");
  if (["pull_request_target", "workflow_run"].includes(eventName))
    throw new Error("Run lint workflows in an unprivileged pull_request, push, or merge_group context");
  const profile = profiles[linter] ?? {};
  const scope = files.trim() || profile.files?.join("\n") || "";
  const onlyShell = shellOnly || profile.shellOnly === true;
  const triggers = [...sharedTriggers, ...(profile.triggers ?? [])];
  if (config) {
    const normalized = path.posix.normalize(config);
    if (path.posix.isAbsolute(normalized) || normalized === ".." || normalized.startsWith("../"))
      throw new Error("config must be repository-relative");
    // A filename supplied as config is literal, even if it contains glob syntax.
    triggers.push(`:(top,literal)${normalized}`);
  }
  const selected = selectFiles(cwd, scope, onlyShell);
  const result = (reason, run = true) => ({ files: run ? selected : [], reason });
  if (!selected.length) return result("no-files", false);
  if (fullScan) return result("full-scan");

  let range;
  try {
    range = comparison(cwd, eventName, event);
  } catch {
    // Missing or shallow history must never produce a false successful skip.
    return result("history-unavailable");
  }
  if (!range) return result("full-event-scan");
  const changed = (specs) => git(cwd, [
    "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "--name-only", "-z",
    range.base, range.head, "--", ...specs,
  ]).split("\0").filter(Boolean);
  try {
    // Deletions and both sides of renames count as changes, including configs.
    if (matchPaths(triggers.join("\n"), changed).length ||
        (triggerFiles.trim() && matchPaths(triggerFiles, changed).length))
      return result("dependencies-changed");
    const affected = matchPaths(scope, changed);
    const current = new Set(selected.map((file) => file.slice(2)));
    const relevant = affected.some((file) => {
      if (!onlyShell || current.has(file) || shellExtension(file)) return true;
      // Deleted/renamed extensionless shell sources can affect remaining scripts.
      try {
        return shellShebang(git(cwd, ["show", `${range.base}:${file}`]).slice(0, 256));
      } catch (error) {
        if (error.status === 128) return false; // New non-shell files have no preimage.
        throw error; // Timeouts or output limits must conservatively select the scope.
      }
    });
    return result(relevant ? "scope-changed" : "unrelated-changes", relevant);
  } catch {
    return result("comparison-unavailable");
  }
}

function booleanInput(name) {
  const value = process.env[`INPUT_${name.toUpperCase()}`] || "false";
  if (!["true", "false"].includes(value)) throw new Error(`${name} must be true or false`);
  return value === "true";
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const event = process.env.GITHUB_EVENT_PATH
      ? JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, "utf8")) : {};
    const { files, reason } = planLint({
      cwd: process.cwd(),
      linter: process.env.INPUT_LINTER ?? "",
      files: process.env.INPUT_FILES ?? "",
      shellOnly: booleanInput("shell-only"),
      fullScan: booleanInput("full-scan"),
      config: process.env.INPUT_CONFIG ?? "",
      triggerFiles: process.env["INPUT_TRIGGER-FILES"] ?? "",
      eventName: process.env.GITHUB_EVENT_NAME ?? "",
      event,
    });
    const directory = mkdtempSync(path.join(process.env.RUNNER_TEMP || tmpdir(), "lint-files-"));
    const list = path.join(directory, "files");
    writeFileSync(list, files.length ? `${files.join("\0")}\0` : "");
    const common = fileURLToPath(new URL("../../../", import.meta.url));
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `any=${files.length > 0}\nreason=${reason}\nfile-list=${list}\ncommon-directory=${common}\n`,
    );
    console.log(`Selected ${files.length} tracked files (${reason}).`);
    if (!files.length)
      console.log("::notice::No applicable files; linter installation and execution are skipped.");
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
