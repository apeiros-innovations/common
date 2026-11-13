# Apeiros Common

Shared lint workflows, local Git hooks, and tool configuration for Apeiros repositories.

## GitHub Actions

Choose the checks your repository needs:

| Workflow                                            | Checks                          |
| --------------------------------------------------- | ------------------------------- |
| [yamllint](.github/workflows/yamllint.yaml)         | YAML files                      |
| [markdownlint](.github/workflows/markdownlint.yaml) | Markdown with markdownlint-cli2 |
| [shellcheck](.github/workflows/shellcheck.yaml)     | Shell scripts                   |
| [actionlint](.github/workflows/actionlint.yaml)     | GitHub Actions workflow syntax  |
| [zizmor](.github/workflows/zizmor.yaml)             | GitHub Actions security         |

Each workflow installs its tools from the selected Common release and checks
the affected file scope. Callers can override file filters, configuration, and
runners. CI does not require Lefthook or a local Mise configuration.

See [workflow selection](docs/workflow-selection.md) for repository path filters and Mise development profiles.

Start with the [workflow guide](docs/shared-lint.md) for usage examples,
change detection, required checks, and runner selection.

### Renovate readiness

The CI gate recognizes dependency PRs from `autoforgex[bot]`, `renovate[bot]`, and
`kumitate-renovate[bot]` on same-repository `renovate/` branches. The dedicated
Kumitate app can publish readiness for existing PRs opened by either legacy bot;
their PR authors stay unchanged during the account migration. A legacy bot cannot
publish readiness for a PR opened by the dedicated app. The newest reported
failure or pending hold remains blocking, and unrelated publishers are rejected.

When upgrading a repository to the dedicated app, update both its shared
`ci-gate` and `retry-renovate-check` action pins to a release containing this
support. Include `kumitate-renovate[bot]` in the retry workflow's status-event
sender filter as well. Test the shared gate and retry actions with:

```sh
node --test tests/ci-gate/*.test.mjs
```

## Local Git hooks

Use [Lefthook](https://lefthook.dev/) to run checks before committing or pushing.
Add `.config/lefthook.yaml` to your repository:

```yaml
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.common.yaml
      - lefthook.github.yaml
```

Replace `vX.Y.Z` with a [published release](https://github.com/apeiros-innovations/common/releases).
Declare Lefthook and the tools your checks need in your project's Mise configuration, then run:

```sh
mise install
mise exec -- lefthook install
```

See [local hook setup](docs/local-hooks.md) for available presets, tool selection,
and overrides. Local hooks and CI workflows can be adopted independently.

## Versions

Pin GitHub workflow calls to a release's full commit SHA with a matching version
comment so Renovate can update them. Pin Lefthook remotes to a release tag.
Read the [changelog](CHANGELOG.md) when upgrading; current tool versions are in
[the Mise configuration](.mise/config.toml).
