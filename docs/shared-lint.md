# Composable lint workflows

Each linter is an independent reusable GitHub Actions workflow. Call only the
workflows needed by a repository and give each its own file scope and optional
configuration override. These workflows run the tools directly. Lefthook is a
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

After `v0.1.0` is published, replace `<release-commit-sha>` below with its full
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
    uses: apeiros-innovations/common/.github/workflows/yamllint.yaml@<release-commit-sha> # v0.1.0
    with:
      files: |
        :(glob)deploy/**/*.yaml
        :(glob)deploy/**/*.yml
        :(glob,exclude)deploy/**/templates/**
      config: .yamllint.yaml
  markdown:
    uses: apeiros-innovations/common/.github/workflows/markdownlint.yaml@<release-commit-sha> # v0.1.0
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
symlinks, submodules, and untracked build output are omitted. An empty match is
a successful no-op, and no tools are installed for that workflow.

The small `lint-files` action only enumerates files and locates the selected
Common release. Each workflow owns its tool installation and direct linter
command. Filenames are passed through NUL-delimited lists with no shell
evaluation. markdownlint-cli2 receives literal file paths and `--no-globs`, so
configuration cannot widen the file scope through its `globs` option. Formatting
changes fail CI instead of being committed.

## Change detection and required checks

The caller decides **when** to run a job. The reusable workflow's `files` input
decides **what** it checks. When selected, it validates every tracked file in
that scope, including on merge queues and manual runs.

For change-based job gating, use the caller's existing `dorny/paths-filter`
selection job and pass its output to the reusable job's `if`. Include the
linter's configuration and the caller workflow in that change filter. A Common
workflow SHA update must select its checks even if no source file changed.
For markdownlint-cli2, include nested `.markdownlint*` configurations too.
Prefer one selection job in the caller over separate change detection in every
reusable workflow.

Keep the required aggregate CI gate running on every PR and `merge_group`.
For conditionally selected jobs, pass the same selection boolean to the gate's
`expected` map so an intentional skip succeeds and an unexpected skip fails.
Avoid workflow-level `paths` filters on a required workflow: a skipped workflow
can leave its required check pending. Repositories without change selection can
call the individual workflows unconditionally; empty scopes skip installation.

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
This change does not broaden runner-group access. Resolve Common's own runner
access before merging this migration: making Common private requires migrating
its public consumers first; keeping it public requires a separately approved
self-hosted runner arrangement for public-repository jobs.

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

`workflow-lint.yaml` remains available for existing callers. New callers compose
the individual workflows. Common's CI calls the five workflows directly, without
running the old combined job a second time. Its initial YAML scope qualifies the
new workflow interfaces; expansion to legacy YAML is a separate cleanup.

## Releases and Renovate

Release Please owns the changelog, tags, and GitHub releases. The requested
tooling line starts at `v0.1.0` through a one-time `Release-As: 0.1.0` commit
footer. Existing `v1.0.0` and `v1.0.1` tags remain published. The release manifest
continues to describe the last published version until the release PR updates
it. During 0.x, features and fixes increment patch; breaking changes increment
minor. No permanent `release-as` configuration is used.

Use the [Common Renovate preset](https://github.com/apeiros-innovations/renovate-config/blob/main/docs/common-tooling.md)
after generic tooling presets. It groups Common workflow updates and permits
all update levels to automerge after required CI passes. For consumers on 0.x,
it excludes the two historical 1.x releases while allowing future major
releases. Existing `main` or historical 1.x consumers need an explicit initial
migration. Local Lefthook remotes can be updated independently; they are not a
prerequisite for adopting the CI workflows.

Publishing a release does not itself schedule the self-hosted Renovate job.
Release-triggered scheduling remains a separate integration.

References: [Git pathspecs](https://git-scm.com/docs/gitglossary#Documentation/gitglossary.txt-aiddefpathspecapathspec),
[Mise locked tools](https://mise.jdx.dev/dev-tools/mise-lock.html),
[markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2),
and [reusing workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows).
