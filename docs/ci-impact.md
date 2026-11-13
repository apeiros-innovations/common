# Select CI work by dependency

Keep required CI entrypoints running for every pull request and merge group.
Select expensive jobs in one preflight and make the required gate enforce that
same selection. This avoids both wasted runner allocations and pending required
checks caused by workflow-level path filters.

The `select-checks` action uses native Git pathspecs for files and Python's
standard TOML parser for Mise tool entries. No package installation, third-party
matching engine, API token, or service is needed. The Linux runner must provide
Git and Python 3.11 or newer. Selection never executes Mise configuration.

## Repository policy

Commit `.github/ci-impact.json` beside the workflows. Keys in `jobs` identify
caller jobs. List direct file dependencies and tools using the exact keys in
Mise configuration and lockfiles. Use `needs` for jobs whose outputs are consumed
by another job; selection includes those dependencies transitively.

```json
{
  "version": 1,
  "ignore_paths": ["README.md"],
  "ignore_tools": ["aqua:betterleaks/betterleaks", "aqua:evilmartians/lefthook"],
  "jobs": {
    "build": {
      "paths": ["src/**", "go.mod", "go.sum", "Dockerfile", ".github/workflows/ci.yaml"],
      "tools": ["go"],
      "needs": []
    },
    "workflows": {
      "paths": [".github/workflows/**", ".github/actions/**"],
      "tools": ["aqua:kjanat/actionlint", "aqua:zizmorcore/zizmor"]
    }
  }
}
```

The example ignores Betterleaks and Lefthook only because neither is used by
these CI jobs. Do not copy that exception into a repository that runs either
tool in CI. Unknown tools run every job unless a group declares `"tools": ["*"]`.
The wildcard is a conservative starting point for jobs with complex tool chains.
Keep tool aliases exact; a new or renamed alias is unclassified and runs all jobs.
Changes to dependent tools must select their consumers too (for example Python
and uv for a pipx-installed linter).

Paths use Git pathspec syntax, not GitHub glob or brace expansion. For example,
`:(glob)**/*.go` matches Go files recursively, and
`:(glob,exclude)docs/**` excludes documentation. Add a positive include when using
exclusions. A matching job dependency wins over `ignore_paths`. Avoid blanket
Markdown exclusions: Markdown can be build input, embedded data, or test fixtures.
New source areas should be mapped in the same PR that introduces them.

By default `.mise/config.toml` and `.mise/mise.lock` are parsed semantically.
A `mise_files` array can list additional TOML configuration and lock files used
by CI. Changes to any non-tool settings, tasks, environment, parser errors, or
added/deleted config files run every job. Tool versions, options, dependencies,
and platform lock/checksum changes select the jobs declaring that tool. Pure
formatting changes do not. Do not exclude settings or task files as local-only
without checking whether CI loads them.

Unclassified files, unclassified tools, changed policy, unavailable history,
and failed comparisons select everything. Malformed policy fails selection and
must fail the required gate. This is intentionally conservative.

## Wire selection and the required gate

Pin the action to a published Common release SHA. During review, consumers can
pin the exact implementation commit; replace it with the release pin before
merging consumers. Keep preflight and consumers in the same workflow:

```yaml
jobs:
  scope:
    runs-on: ubuntu-26.04
    permissions:
      contents: read
    outputs:
      selected: ${{ steps.select.outputs.selected }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          fetch-depth: 0
          persist-credentials: false
      - id: select
        uses: apeiros-innovations/common/.github/actions/select-checks@<release-sha>
  build:
    needs: scope
    if: needs.scope.result == 'success' && fromJSON(needs.scope.outputs.selected || '{}').build
    runs-on: ubuntu-26.04
    steps:
      # Existing build steps.
      - run: echo "Replace with the repository build"
```

Retain the repository's existing runner selection. Public callers use standard
GitHub-hosted runners; private Apeiros callers use `gha-shared` / `gha-linux-k8s`.
Add `scope` to the required gate's `needs` and `"scope": true` to its `expected`
map. Replace the build's expected boolean with the identical selection condition.
Preserve existing draft, fork, event, and matrix conditions in both places.
Never treat arbitrary skipped jobs as successful. A selected job that fails,
is cancelled, or unexpectedly skips must block merging. When gating dependent
jobs independently, account explicitly for intentional skipped dependencies.

For existing component selectors, this preflight can gate the caller while the
component selector continues choosing the affected modules or matrix entries.
Do not duplicate component-selection logic in the organization policy.

## Events and rollout

| Event | Comparison |
| --- | --- |
| Pull request | Merge base to PR head, including all commits in the PR |
| Existing branch push | Exact before-to-after range, including all pushed commits |
| Merge group | Exact merge-group base-to-head range |
| Manual, schedule, tag, new branch | Full selection |
| Missing or shallow comparison history | Full selection |

Deleted paths and both sides of renames participate. Git uses NUL-delimited
filenames and argument arrays; no shell interpolation of event data or paths is
performed. Privileged `pull_request_target` and `workflow_run` events are rejected.
This does not change runner isolation or permission requirements for PR code.

Keep release/version management, maintenance schedules, PR-title checks, and
explicit manual operations on their native event contracts. For an optional
standalone publishing workflow, workflow-level path filters are appropriate only
when the complete transitive build inputs can be expressed safely and that check
is not required. Shared tool manifests usually need job-level semantic selection.

For each adoption, replay representative changes: docs, one source component,
relevant and unrelated tools, tool lock changes, workflow edits, deletions,
renames, unknown files, multi-commit PRs/pushes, missing baselines, and merge queues.
Run the shared behavior tests with:

```sh
python3 -m unittest discover -s tests/select-checks -v
```

GitHub documents [required-check skipping](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks),
[job conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions),
and [event comparisons](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#git-diff-comparisons).
See also [Git diff](https://git-scm.com/docs/git-diff),
[Git pathspecs](https://git-scm.com/docs/gitglossary#Documentation/gitglossary.txt-aiddefpathspecapathspec),
and [Mise lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html).
