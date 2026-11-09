# Local Git hooks

Common provides reusable [Lefthook](https://lefthook.dev/) checks for commits and
pushes. Start with the [README example](../README.md#local-git-hooks), then select
the presets and tools your project needs.

## Choose checks

`lefthook.common.yaml` provides general formatting, linting, staged-secret checks,
and repository checks. Add language or project presets alongside it:

| Preset | Purpose |
| --- | --- |
| [javascript](../lefthook.javascript.yaml) | JavaScript and TypeScript formatting and linting |
| [astro](../lefthook.astro.yaml) | Astro formatting, checks, and builds |
| [python](../lefthook.python.yaml) | Ruff fixes, formatting, and linting |
| [django](../lefthook.django.yaml) | Django template formatting and linting |
| [go](../lefthook.go.yaml) | Go formatting, linting, module metadata, tests, and vulnerabilities |
| [container](../lefthook.container.yaml) | Dockerfile linting and scanning |
| [github](../lefthook.github.yaml) | Actionlint and Zizmor |
| [helm](../lefthook.helm.yaml) | Helm documentation and linting |
| [opentofu](../lefthook.opentofu.yaml) | OpenTofu formatting, documentation, locks, and validation |
| [terragrunt](../lefthook.terragrunt.yaml) | Terragrunt formatting, locks, and validation |
| [poetry](../lefthook.poetry.yaml) | Poetry configuration and lock validation, plus Pylint |
| [renovate](../lefthook.renovate.yaml) | Renovate configuration validation |
| [devskim](../lefthook.devskim.yaml) | DevSkim with a project configuration |

For a smaller selection, replace `lefthook.common.yaml` with
[`lefthook.base.yaml`](../lefthook.base.yaml) and individual files from
[`lefthook/`](../lefthook/). Load the base once and include each check through
only one preset or file; duplicate inclusions cause Lefthook errors.

Spelling, commit-message checks, signed-commit checks, and dependency scanning
are optional. Select `lefthook/cspell.yaml`, `lefthook/cspell-repository.yaml`,
`lefthook/commitlint.yaml`, `lefthook/signed-commits.yaml`, or
`lefthook/osv-scanner.yaml` explicitly when needed.

## Install tools

The consuming project owns its tool versions. Declare Lefthook and the tools
used by your selected checks in `.mise/config.toml`; use
[Common's tool configuration](../.mise/config.toml) as the reference. Include
required runtimes and backend options, and choose versions compatible with your
project. Install project-managed dependencies through its package manager.

```sh
mise trust
mise install
mise lock
mise exec -- lefthook install
mise exec -- lefthook validate
mise exec -- lefthook dump
```

Commit the configuration, lockfile, and generated dependency graphs together.
Inspect `lefthook dump` to confirm the expected checks loaded: validation alone
does not prove that every remote file was found. A Lefthook remote uses a
release tag; a raw commit SHA cannot be used for its initial branch-based clone.

Updating the Common hook release does not update the project's tool versions.
Renovate can maintain those separately. The reusable CI workflows instead use
Common's own locked tools.

## Customize a check

Override shared jobs by name in the repository's primary Lefthook configuration.
For example, append this alongside `remotes` to skip the local Zizmor check:

```yaml
pre-commit:
  jobs:
    - name: validate
      group:
        jobs:
          - name: zizmor
            skip: true
```

Use the same path to override `exclude`, `env`, or `run`. Match the full nesting
shown by `lefthook dump`. Keep team settings in the tracked configuration and
personal settings in `.config/lefthook-local.yaml`.

Pre-commit runs formatting, generation, then validation. Mutating checks run
sequentially; validation runs in parallel. Each check selects files and project
prerequisites through its own `glob`, `exclude`, `file_types`, and `only` settings.
Unmatched checks are skipped.

For checks with a configuration prerequisite, export configuration overrides
before running Lefthook. Its `only.run` probe runs before per-job `env` is applied.
If an override supplies the configuration through job `env`, set `only: true`
for that job; file filters still apply and the helper validates the configuration.

See Lefthook's [remote configuration](https://lefthook.dev/configuration/remotes/)
and [configuration reference](https://lefthook.dev/configuration/) for additional options.
