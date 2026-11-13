# Run workflows for relevant changes

Use `dorny/paths-filter` to select jobs from their file dependencies. Keep filters
in `.github/paths/<workflow>.yaml`, and use the same decisions in each job's `if`
and the required CI gate's `expected` map. The repository owns these plain filter
files; no shared selector action, custom policy format, or Common release is
required.

## Choose an existing action

| Action | Purpose | Organization use |
| --- | --- | --- |
| [dorny/paths-filter](https://github.com/dorny/paths-filter) | Named file filters and boolean job/step outputs | Default for change detection; already used across Apeiros |
| [tj-actions/changed-files](https://github.com/tj-actions/changed-files) | Detailed inventories of added, modified, deleted, and renamed files | Retain where existing build logic needs those inventories |
| [fkirc/skip-duplicate-actions](https://github.com/fkirc/skip-duplicate-actions) | Find prior successful or concurrent runs for equivalent content | Consider separately when repeated equivalent runs are the problem |

Pin actions to full release SHAs with version comments for Renovate. Preserve
existing component selectors and matrix planning when they already select the
appropriate modules or packages.

## Separate local tools from CI inputs

A file filter cannot distinguish Betterleaks from OpenTofu when both versions
live in the same file. Put local-only tools such as Lefthook, Betterleaks, and
Commitlint in `.mise/config.dev.toml`, with their entries in `.mise/mise.dev.lock`.
Keep shared build tools in `.mise/config.toml` and `.mise/mise.lock`.

Mise supports environment-specific configuration and lockfiles natively. Existing
`.miserc.toml` files with `env = ["dev"]` activate the development profile for
local work. Set `MISE_ENV: ci` in CI workflows so local hooks and tools are not
part of CI's inputs. Local installation remains `mise install --locked`.

Move exact tool declarations and lock entries together, preserving versions,
platforms, checksums, backend options, and dependency graphs. Run `mise lock`
with the development environment active when adding or updating a local tool.
A tool belongs in the shared configuration if any CI job actually uses it.

Changes to the shared manifest/lock must select its consumers. Development-only
changes can skip builds, but jobs that format or validate those files must still
include them. This trades per-tool semantic comparisons for clear file ownership
and ordinary upstream path filtering.

See [Mise config environments](https://mise.jdx.dev/configuration/environments.html)
and [environment lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html#environment-specific-lockfiles).

## Wire filters and required checks

A filter file contains native upstream patterns:

```yaml
catalog:
  - 'modules/**'
  - 'units/**'
  - 'stacks/**'
  - 'test/**'
  - '.mise/config.toml'
  - '.mise/mise.lock'
  - '.github/workflows/**'
  - '.github/paths/**'
ansible:
  - 'ansible/**'
  - '.github/workflows/ansible.yaml'
  - '.github/paths/**'
```

Use one small `changes` or `scope` job with checkout `fetch-depth: 0` and
`persist-credentials: false`, then call `dorny/paths-filter`. Use
`predicate-quantifier: some-with-excludes` when the rules contain exclusions.
The caller's boolean outputs must also select producer jobs when a selected
consumer needs their outputs, such as a tool-version job.

Keep the required entrypoint running on every PR and merge group. Add the change
selection job to the required gate's `needs` and require it to succeed. Preserve
existing fork, draft, event, and matrix conditions in both execution and gate
expectations. Unexpected skipped, failed, or cancelled selected jobs still block
merging. A detector failure must never become an unrelated-change success.

Use an `unclassified` filter for paths not assigned to a job or intentionally
ignored; matching it selects every family. Changes to `.github/paths/**` select
all relevant checks so edits to reusable-workflow filters also exercise callers.
Watch configurations and shared build dependencies as well as source files.
Markdown can be a build input or fixture, so avoid blanket Markdown exclusions.

## Compare complete event ranges

The upstream action supports PRs, pushes, and merge queues. With `token: ""`, it
uses local Git comparison without API permissions. Provide the PR base/head,
push before/after, or merge-group base/head. PR comparison uses the merge base
and includes all commits, so an unrelated follow-up commit cannot hide an
unresolved earlier source change.

Manual, scheduled, tag, and new-branch events select the full scope. Check that
comparison commits are available before invoking the filter. If history is
missing, or a push comparison is not an ancestor range, select the full scope.
This small workflow condition uses Git directly; the action owns file discovery
and glob matching.

Release/version management and explicit manual operations retain their event
contracts. Optional standalone publishing workflows can use this same job
selection when shared manifests make workflow-level path filters too coarse.

For each adoption, verify source, docs, shared tool, development tool, lockfile,
workflow, unknown-file, rename/deletion, multi-commit, and merge-group changes.
Check both selected jobs and the required gate. A passing configuration check
does not establish that a deployment or integration suite has passed.

GitHub documents [job conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)
and [required-check skipping](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).
