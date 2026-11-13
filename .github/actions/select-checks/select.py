"""Dependency selection without tool installation, API tokens, or shell evaluation."""

import json
import os
from pathlib import Path
import re
import subprocess
import tomllib


def git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=30,
    ).stdout


def comparison(cwd, event_name, event):
    if event_name in ("pull_request_target", "workflow_run"):
        raise ValueError("Use unprivileged PR, push, or merge-group workflows")
    if event_name == "pull_request":
        base = event.get("pull_request", {}).get("base", {}).get("sha")
        head = event.get("pull_request", {}).get("head", {}).get("sha")
    elif event_name == "merge_group":
        base = event.get("merge_group", {}).get("base_sha")
        head = event.get("merge_group", {}).get("head_sha")
    elif event_name == "push" and not event.get("created") and not event.get("ref", "").startswith("refs/tags/"):
        base, head = event.get("before"), event.get("after")
    else:
        return None
    for sha in (base, head):
        if not isinstance(sha, str) or not re.fullmatch(r"[a-fA-F0-9]{40}|[a-fA-F0-9]{64}", sha) or set(sha) == {"0"}:
            return None
        git(cwd, "rev-parse", "--verify", sha + "^{commit}")
    if event_name == "pull_request":
        base = git(cwd, "merge-base", base, head).decode().strip()
    return base, head


def validate(policy):
    if policy.get("version") != 1 or not isinstance(policy.get("jobs"), dict) or not policy["jobs"]:
        raise ValueError("Policy requires version 1 and nonempty jobs")
    def strings(value):
        return isinstance(value, list) and all(isinstance(v, str) and v for v in value)
    for key in ("ignore_paths", "ignore_tools", "mise_files"):
        if not strings(policy.get(key, [])):
            raise ValueError("Invalid " + key)
    for name, rule in policy["jobs"].items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name) or not isinstance(rule, dict):
            raise ValueError("Invalid job rule")
        for key in ("paths", "tools", "needs"):
            if not strings(rule.get(key, [])):
                raise ValueError("Invalid job " + key)
        if set(rule.get("needs", [])) - policy["jobs"].keys():
            raise ValueError("Unknown dependency")


def select(cwd, policy, event_name, event, policy_path=".github/ci-impact.json"):
    validate(policy)
    if event_name in ("pull_request_target", "workflow_run"):
        raise ValueError("Use unprivileged PR, push, or merge-group workflows")
    jobs = policy["jobs"]
    full = lambda reason: ({name: True for name in jobs}, reason)
    try:
        bounds = comparison(cwd, event_name, event)
        if bounds is None:
            return full("full event or missing baseline")
        base, head = bounds

        def diff(specs):
            return set(git(cwd, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                           "--name-only", "-z", base, head, "--", *specs).decode().split("\0")) - {""}

        def match(specs):
            if not specs:
                return set()
            # Git 2.52 needs exclusions applied to the root inventory when an
            # exclusion lives outside a fixed directory include's prefix.
            excludes = [s for s in specs if re.match(r"^:(?:!|\^|\([^)]*\bexclude\b[^)]*\))", s)]
            includes = [s for s in specs if s not in excludes]
            found = diff(includes or [":(top,glob)**"])
            return found & diff([":(top,glob)**", *excludes]) if excludes else found

        changed = diff([])
        if policy_path in changed:
            return full("dependency policy changed")
        mise_files = set(policy.get("mise_files", [".mise/config.toml", ".mise/mise.lock"]))
        changed_tools = set()
        for file in changed & mise_files:
            # Parse data only: never activate Mise, templates, hooks, or tasks.
            old = tomllib.loads(git(cwd, "show", f"{base}:{file}").decode())
            new = tomllib.loads(git(cwd, "show", f"{head}:{file}").decode())
            old_tools, new_tools = old.pop("tools", {}), new.pop("tools", {})
            if old != new:
                return full("shared Mise settings changed")
            changed_tools.update(k for k in old_tools.keys() | new_tools.keys()
                                 if old_tools.get(k) != new_tools.get(k))
        changed_tools -= set(policy.get("ignore_tools", []))
        covered = match(policy.get("ignore_paths", [])) | mise_files
        selected = {}
        mapped_tools = set()
        for name, rule in jobs.items():
            paths = match(rule.get("paths", [])) - mise_files
            covered |= paths
            tool_names = set(rule.get("tools", []))
            mapped_tools |= tool_names
            selected[name] = bool(paths or (changed_tools if "*" in tool_names else changed_tools & tool_names))
        if changed - covered:
            return full("unclassified file change")
        if "*" not in mapped_tools and changed_tools - mapped_tools:
            return full("unclassified tool change")
        # Dependencies must run when a selected consumer needs their outputs.
        while True:
            required = {dep for name, rule in jobs.items() if selected[name] for dep in rule.get("needs", [])}
            missing = {dep for dep in required if not selected[dep]}
            if not missing:
                break
            selected.update({dep: True for dep in missing})
        return selected, "file and tool dependencies"
    except (subprocess.SubprocessError, UnicodeError, tomllib.TOMLDecodeError, OSError, TypeError, AttributeError):
        return full("comparison unavailable or unsupported Mise data")


def main():
    root = Path.cwd()
    relative = os.environ.get("SELECT_POLICY", ".github/ci-impact.json")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or Path(relative).is_absolute():
        raise ValueError("Policy must be inside the repository")
    policy = json.loads(path.read_text())
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    selected, reason = select(root, policy, os.environ["GITHUB_EVENT_NAME"], event, relative)
    encoded = json.dumps(selected, separators=(",", ":"))
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write("selected=" + encoded + "\n")
    print(reason + ": " + encoded)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write("### Selected checks\n\n" + reason + "\n\n```json\n" + encoded + "\n```\n")


if __name__ == "__main__":
    main()
