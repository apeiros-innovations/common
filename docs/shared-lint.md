# Composable lint workflows

Each linter is an independent reusable GitHub Actions workflow. Call only the
workflows needed by a repository and give each its own file scope, additional
dependency paths, and optional configuration override. These workflows run the tools directly. Lefthook is a
separate local Git-hook integration and is not installed, invoked, or read by CI.

| Workflow            | Tool              | Default scope                                                        |
| ------------------- | ----------------- | -------------------------------------------------------------------- |
| `yamllint.yaml`     | yamllint          | Tracked YAML; excludes templates and generated Mise environments     |
| `markdownlint.yaml` | markdownlint-cli2 | Tracked `.md` and `.markdown`; excludes the generated changelog      |
| `shellcheck.yaml`   | ShellCheck        | Shell extensions and shell shebangs, including extensionless scripts |
| `actionlint.yaml`   | Actionlint        | `.github/workflows/*.yaml` and `.yml`                                |
| `zizmor.yaml`       | Zizmor            | Workflows, local action manifests, and Dependabot configuration      |

All default scopes exclude `node_modules`, `vendor`, `.venv`, and `.mise/locks`.
Zizmor uses online audits by default; `offline: true` is an explicit opt-out.

## Compose the checks

After `v1.1.0` is published, replace `<release-commit-sha>` below with its full
commit SHA. The version comment lets Renovate track releases:

```yaml
name: Lint
on:
  pull_request: {}
  merge_group: {}
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  yaml:
    uses: apeiros-innovations/common/.github/workflows/yamllint.yaml@<release-commit-sha> # v1.1.0
    with:
      files: |
        :(glob)deploy/**/*.yaml
        :(glob)deploy/**/*.yml
        :(glob,exclude)deploy/**/templates/**
      config: .yamllint.yaml
  markdown:
    uses: apeiros-innovations/common/.github/workflows/markdownlint.yaml@<release-commit-sha> # v1.1.0
    with:
      files: |
        README.md
        :(glob)docs/**/*.md
      config: .markdownlint-cli2.yaml
```

Both `files` and `config` are optional. Omitting `files` uses the workflow's
default scope. Omitting `config` uses the policy bundled with the selected
Common release. An explicit config must exist; a missing file fails the linter.
Tool-native nested configuration behavior, such as markdownlint-cli2's
per-directory overrides, still applies.

`files` is a newline-separated list of native **Git pathspecs**. `:(glob)` enables
Git's recursive glob syntax, and `:(glob,exclude)` removes matching files. Git
does not expand brace alternatives: use separate lines for `*.yaml` and `*.yml`.
A custom `files` input replaces the entire default list, including exclusions.
Only tracked, existing regular files are passed to a linter. Deleted files,
symlinks, submodules, and untracked build output are omitted from linter arguments.
Deleted and renamed paths still participate in change detection. An empty or
unaffected scope is a successful no-op; no linter tools are installed or run.

The `lint-files` action checks whether a scope was affected, enumerates its
files, and locates the selected Common release. Its bundled `profiles.json`
defines default scopes and config dependencies once for both preflight and lint
execution. Each workflow owns its tool installation and direct linter
command. Filenames are passed through NUL-delimited lists with no shell
evaluation. markdownlint-cli2 receives literal file paths and `--no-globs`, so
configuration cannot widen the file scope through its `globs` option. Formatting
changes fail CI instead of being committed.

## Change detection and required checks

Change detection is built into each reusable workflow. It compares the event's
commits before installing tools. If no selected file or dependency changed, it
skips installation and lint execution. If the scope was affected, it checks
**all existing files in that scope**. This catches effects on unchanged peers,
such as scripts that source a changed shell file or shared Markdown rules.

| Event or change | Behavior |
| --- | --- |
| Pull request | Compare the PR merge base with the current PR head (the full PR diff). |
| Existing-branch push | Compare the event's `before` and `after` commits, including every pushed commit. |
| Merge queue | Compare `merge_group.base_sha` with `merge_group.head_sha`. |
| Config, workflow, local action, or tool-lock change | Recheck the affected linter's complete file scope. |
| Manual, scheduled, tag, or new-branch run | Check the complete scope. |
| Missing commits, shallow history, or unavailable diff | Check the complete scope; never infer a successful skip. |

The default dependency triggers cover `.github/workflows/**` (including Common
SHA updates and `actions.lock`), `.github/actions/**`, `.mise/**`, and Common's
selector tests. Each profile adds its linter's configuration paths, including
nested Markdown configs. The explicit `config` path is also watched, including
its deletion. Add repository-specific dependencies with `trigger-files`, using
the same Git pathspec syntax as `files`, for example:

```yaml
with:
  files: ":(glob)docs/**/*.md"
  trigger-files: |
    rules/markdown/**
    tools/generate-docs.mjs
  config: .markdownlint-cli2.yaml
```

`trigger-files` extends the built-in triggers. `full-scan: true` bypasses change
detection and checks the complete selected scope. Automatic comparison needs
Git history; the workflows use checkout with `fetch-depth: 0`. A preselected
`full-scan` invocation needs only a single-commit checkout.

The PR comparison deliberately includes earlier commits: adding an unrelated
commit must not turn an earlier lint failure into a successful skip. This does
not reuse a previous passing result or promise to skip a rerun of the same PR.
Such reuse would require a separately validated result cache covering source,
configuration, tool versions, and workflow behavior.

### Skip entire jobs with one preflight

An action runs after its job has acquired a runner. To avoid allocating a
separate runner for each unaffected linter, run `lint-files` in one shared
preflight job and use its `any` output in each caller job's `if`. Common performs
this preflight in its existing shared-action test job. The required aggregate
gate checks the same selection decisions, so intended skips pass and unexpected
skips or preflight failures fail.

For a consumer, the Markdown portion of this pattern is:

```yaml
jobs:
  changes:
    runs-on:
      group: gha-shared
      labels: gha-linux-k8s
    permissions:
      contents: read
    outputs:
      markdownlint: ${{ steps.markdownlint.outputs.any }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          persist-credentials: false
          fetch-depth: 0
      - id: markdownlint
        uses: apeiros-innovations/common/.github/actions/lint-files@<release-commit-sha> # v1.1.0
        with:
          linter: markdownlint
  markdownlint:
    needs: changes
    if: needs.changes.outputs.markdownlint == 'true'
    uses: apeiros-innovations/common/.github/workflows/markdownlint.yaml@<release-commit-sha> # v1.1.0
    with:
      full-scan: true
```

Repeat the preflight step for the linters a repository uses. Pass identical
`files`, `config`, and `trigger-files` overrides to preflight and execution, and
pin both to the same Common release. Common uses a YAML anchor for its custom
YAML scope to avoid duplicating that value. Keep the required aggregate gate
running on every PR and `merge_group`, with the preflight job required to succeed
and each linter's selection boolean included in the gate's `expected` map.

Avoid workflow-level `paths` filters on a required workflow: GitHub can leave its
required check pending when that workflow is skipped. Git diff comparison here
uses the local repository rather than GitHub's path-filter file-list limit.

## Security properties

The selector uses JavaScript argument arrays and NUL-delimited file lists; it
never constructs shell commands from filenames or event values. Commit inputs
must be full hexadecimal SHAs. Diff commands disable external diff programs and
text conversion. The selector needs no token, API requests, or write permissions.
It rejects `pull_request_target` and `workflow_run` invocations; linting belongs
in the unprivileged PR, push, and merge-queue workflows.

Checkout keeps `persist-credentials: false`. Lint workflows retain only
`contents: read`, pinned third-party action SHAs, and trusted Common tool locks.
These controls do not make untrusted code safe on an internal self-hosted runner;
the runner access and isolation requirements below still apply.

GitHub's security reference now recommends native action dependency lockfiles
where available. `.github/workflows/actions.lock` covers action dependencies,
including transitive dependencies; reusable workflow calls still need full SHA
pins. Lockfile adoption and its Renovate update path remain separate work. Any
lockfile change already invalidates these lint selections.

## Self-hosted runners

All workflows in Common use the organization's self-hosted Linux runners:

```yaml
runs-on:
  group: gha-shared
  labels: gha-linux-k8s
```

There is no GitHub-hosted fallback. Reusable workflows use runner access from the
calling repository; the caller must have access to `gha-shared`. Publishing
Common publicly does not grant outside repositories access to these runners.

Foundry currently declares `allowsPublicRepositories: false` for `gha-shared`.
Private Apeiros callers can use these workflows, but public callers, including
Common's own CI while Common remains public, cannot use that runner group.
This configuration does not broaden runner-group access. Common's CI and release
jobs need a self-hosted runner arrangement that permits its public repository.
Making Common private requires migrating its public consumers first; keeping it
public requires a separately approved runner arrangement for public-repository jobs.

Public repositories cannot consume private shared actions or reusable
workflows through cross-repository `uses` references. Public-repository jobs
that execute untrusted contributions need an isolated runner pool; do not open
the shared internal runner group to public repositories to bypass this limit.
Ephemeral runners alone do not isolate their network, credentials, or host.

See GitHub's [runner access rules](https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations#how-reusable-workflows-use-runners)
and [self-hosted runner security guidance](https://docs.github.com/en/actions/reference/security/secure-use#hardening-for-self-hosted-runners).

## Versions and permissions

The selected Common release owns the linter versions, runtime versions, locks,
and default configuration. Each workflow installs only its tools from Common's
Mise manifest with `--locked`, then runs those installed binaries against the
consumer checkout. The consumer does not need Mise configuration or Lefthook.
Upgrading one Common workflow SHA upgrades that workflow's tools and defaults.

The workflows require only `contents: read`. Checkout does not persist
credentials. Zizmor receives the read-only token for online audits; other
linters need no token or secrets. No workflow requests OIDC or write access.

`workflow-lint.yaml` remains as a compatibility wrapper for existing callers. It
delegates to the individual Actionlint, ShellCheck, and Zizmor workflows, using
Common's locked tools and defaults. Its final `lint` job preserves the aggregate
check and fails if any delegated job fails or is cancelled. New callers compose
the individual workflows to set independent scopes and configuration overrides.
Common's CI calls the five workflows directly, without running the wrapper again.
Its YAML scope includes the new interfaces and the compatibility wrapper;
expansion to other legacy YAML is a separate cleanup.

## Releases and Renovate

Release Please owns the changelog, tags, and GitHub releases. The composable
lint workflows target `v1.1.0`, following the existing `v1.0.1` release. A
one-time `Release-As: 1.1.0` commit footer selects this version and supersedes
the earlier 0.x proposal. Existing release tags remain unchanged. The release
manifest continues to describe the last published version until the release PR
updates it. Subsequent releases use normal semantic versioning: fixes increment
patch, features increment minor, and breaking changes increment major. No
permanent `release-as` configuration is used.

Use the [Common Renovate preset](https://github.com/apeiros-innovations/renovate-config/blob/main/docs/common-tooling.md)
after generic tooling presets. It groups Common workflow updates and permits
all update levels to automerge after required CI passes. Existing version-pinned
consumers can move forward from `v1.0.1` to `v1.1.0` through normal Renovate
updates; no historical-version exclusions are needed. Consumers following
`main` need an explicit migration to a release SHA with a version comment.
Adopting the new individual workflow paths is also an explicit migration. Local
Lefthook remotes can be updated independently of the CI workflows.

Publishing a release does not itself schedule the self-hosted Renovate job.
Release-triggered scheduling remains a separate integration.

References: [workflow syntax and diff comparisons](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#git-diff-comparisons),
[secure use](https://docs.github.com/en/actions/reference/security/secure-use),
[workflow dependency lockfiles](https://docs.github.com/en/actions/concepts/security/workflow-dependency-lockfiles),
[Git diff](https://git-scm.com/docs/git-diff),
[checkout history](https://github.com/actions/checkout#fetch-all-history-for-all-tags-and-branches),
[Git pathspecs](https://git-scm.com/docs/gitglossary#Documentation/gitglossary.txt-aiddefpathspecapathspec),
[Mise locked tools](https://mise.jdx.dev/dev-tools/mise-lock.html),
[markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2),
and [reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
