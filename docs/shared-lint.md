# Shared lint workflow

`.github/workflows/lint.yaml` runs the same Lefthook `ci` checks as a local
`lefthook run pre-commit --tag ci --all-files`. Consumers select profiles in
Lefthook and own tool versions in Mise. Common owns the execution contract.

After the first release of this interface, call it using that release's full
commit SHA with a version comment for Renovate:

```yaml
jobs:
  lint:
    uses: apeiros-innovations/common/.github/workflows/lint.yaml@<release-commit-sha> # v0.1.0
    permissions:
      contents: read
    with:
      tools: aqua:kjanat/actionlint aqua:koalaman/shellcheck aqua:zizmorcore/zizmor
      expected-checks: '["actionlint", "shellcheck", "zizmor"]'
```

Replace the placeholder only after `v0.1.0` is published. Node and
`aqua:evilmartians/lefthook` are always installed. Declare those exact keys and
every listed tool in the consumer's Mise configuration, commit their Linux x64
locks, and include runtime dependencies such as Python when checks need them.
The workflow rejects undeclared keys instead of resolving a short tool alias to
an unintended backend. It installs only these tools with `--locked`.

The example expects a Lefthook configuration selecting the base, GitHub checks,
and ShellCheck. For the normal project profile, list the tools needed by all its
`ci` jobs, including formatters. `expected-checks` is a nonempty JSON array of
required leaf job names. The guard rejects missing jobs, disabled jobs/groups,
and jobs without the `ci` tag. This catches incomplete remote fetches; Lefthook
still decides whether each loaded check has applicable files.

An optional `config` input selects a repository-relative Lefthook file. Common
uses `.github/lint.lefthook.yaml` to exercise the workflow with a focused profile.
Extends paths in that file are relative to the repository root. The default is
normal Lefthook config discovery.

## Execution and permissions

The workflow checks all tracked files. Formatters may edit the checkout, but
`--fail-on-changes` makes that a failure and `--no-stage-fixed` prevents automatic
staging. Generators without the `ci` tag are not selected. Build and integration
tests remain separate jobs. Callers should include this job in their required
CI gate and run it on `pull_request` and `merge_group` where applicable.

Only `contents: read` is required. Credentials are not persisted by checkout,
and the workflow does not request secrets, write tokens, or OIDC tokens. Private
Lefthook remotes need a separately designed read-only authentication setup.

The existing `workflow-lint.yaml` remains compatible for current callers. Its
reviewdog annotations, shebang discovery, and online Zizmor scan differ from the
Lefthook profile. The new workflow inherits the local Zizmor helper's **offline**
mode and file globs. Migrate callers after checking those coverage differences;
do not run both copies of the same check indefinitely. Common exercises both
during this initial rollout.

## Releases and consumer updates

Release Please manages the release PR, changelog, tag, and GitHub release. The
new tooling line starts at `v0.1.0` using a one-time `Release-As: 0.1.0` commit
footer. Existing `v1.0.0` and `v1.0.1` tags are preserved. The release manifest
continues to describe the last published version until the release PR updates
it. Do not leave a permanent `release-as` override in the configuration.

During 0.x, fixes and features increment the patch version; breaking changes
increment the minor version. The historical 1.0.0 and 1.0.1 versions must be
excluded from Renovate's candidate releases for consumers of the new line.
That exclusion does not prevent future major updates or their automerge.
Use the [Common consumer preset](https://github.com/apeiros-innovations/renovate-config/blob/main/docs/common-tooling.md)
after generic tooling presets. Existing consumers on `main` or the historical
1.x line need an explicit first migration to the new release.

Pin Lefthook remotes to the same release tag as the workflow's version comment:

```yaml
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    # renovate: datasource=github-tags depName=apeiros-innovations/common
    ref: v0.1.0
    configs:
      - lefthook.base.yaml
      - lefthook.github.yaml
      - lefthook/shellcheck.yaml
```

Renovate's GitHub Actions manager updates the workflow SHA and version comment;
the organization's annotated manager updates the Lefthook tag. Group these
updates under one Common dependency update, permit all version levels to
automerge, and require the consumer's CI gate to pass. Tool version updates
remain separate Mise dependencies. Publishing a release does not by itself
schedule the self-hosted Renovate job; release-triggered scheduling is a separate
integration.

References: [Lefthook run](https://lefthook.dev/usage/commands/run/),
[Mise lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html),
[Release Please version overrides](https://github.com/googleapis/release-please#how-do-i-change-the-version-number),
and [Renovate GitHub Actions](https://docs.renovatebot.com/modules/manager/github-actions/).
