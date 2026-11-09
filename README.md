# Apeiros Common

Shared lint workflows, local Git hooks, and tool configuration for Apeiros repositories.

## GitHub Actions

Choose the checks your repository needs:

| Workflow | Checks |
| --- | --- |
| [yamllint](.github/workflows/yamllint.yaml) | YAML files |
| [markdownlint](.github/workflows/markdownlint.yaml) | Markdown with markdownlint-cli2 |
| [shellcheck](.github/workflows/shellcheck.yaml) | Shell scripts |
| [actionlint](.github/workflows/actionlint.yaml) | GitHub Actions workflow syntax |
| [zizmor](.github/workflows/zizmor.yaml) | GitHub Actions security |

Each workflow installs its tools from the selected Common release and checks
the affected file scope. Callers can override file filters, configuration, and
runners. CI does not require Lefthook or a local Mise configuration.

Start with the [workflow guide](docs/shared-lint.md) for usage examples,
change detection, required checks, and runner selection.

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
