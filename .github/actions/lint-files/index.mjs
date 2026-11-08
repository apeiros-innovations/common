import { execFileSync } from "node:child_process";
import {
  appendFileSync,
  closeSync,
  lstatSync,
  mkdtempSync,
  openSync,
  readSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export function selectFiles(cwd, input, shellOnly = false) {
  const patterns = input
    .split(/\r?\n/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (!patterns.length) throw new Error("files must contain at least one Git pathspec");
  // Git owns path matching; no shell expansion or evaluation of filenames.
  const list = (specs) =>
    execFileSync("git", ["ls-files", "-z", "--", ...specs], {
      cwd,
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    })
      .split("\0")
      .filter(Boolean);
  const isExclusion = (pattern) => /^:(?:!|\^|\([^)]*\bexclude\b[^)]*\))/.test(pattern);
  const includes = patterns.filter((pattern) => !isExclusion(pattern));
  const excludes = patterns.filter(isExclusion);
  const tracked = list(includes.length ? includes : [":(top,glob)**"]);
  // Apply exclusions to the root inventory. Git 2.52 otherwise drops a fixed
  // directory scope when an exclusion lies outside that directory's prefix.
  const allowed = excludes.length ? new Set(list([":(top,glob)**", ...excludes])) : null;
  return [...new Set(tracked)]
    .filter((file) => {
      if (allowed && !allowed.has(file)) return false;
      const absolute = path.join(cwd, file);
      try {
        if (!lstatSync(absolute).isFile()) return false;
      } catch (error) {
        if (error.code === "ENOENT") return false;
        throw error;
      }
      if (!shellOnly || /\.(?:sh|bash|bats|ksh)$/.test(file)) return true;
      const fd = openSync(absolute, "r");
      try {
        const buffer = Buffer.alloc(256);
        const bytes = readSync(fd, buffer, 0, buffer.length, 0);
        return /^#![^\r\n]*\b(?:sh|bash|dash|ksh|ash)\b/.test(buffer.subarray(0, bytes).toString());
      } finally {
        closeSync(fd);
      }
    })
    .map((file) => `./${file}`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const files = selectFiles(
      process.cwd(),
      process.env.INPUT_FILES ?? "",
      process.env["INPUT_SHELL-ONLY"] === "true",
    );
    const directory = mkdtempSync(path.join(process.env.RUNNER_TEMP || tmpdir(), "lint-files-"));
    const list = path.join(directory, "files");
    writeFileSync(list, files.length ? `${files.join("\0")}\0` : "");
    const common = fileURLToPath(new URL("../../../", import.meta.url));
    appendFileSync(
      process.env.GITHUB_OUTPUT,
      `any=${files.length > 0}\nfile-list=${list}\ncommon-directory=${common}\n`,
    );
    console.log(`Selected ${files.length} tracked files.`);
    if (!files.length)
      console.log("::notice::No applicable files; linter installation and execution are skipped.");
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
