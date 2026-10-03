# Apeiros Common

Shared development-tooling policy for Apeiros repositories.

> [!warning]
> This project is experimental. Consumers should upgrade the shared configuration intentionally.

Common provides reusable [Lefthook](https://lefthook.dev/) checks, presets, tool definitions, and shared formatter and linter configuration.

## Composition

| Layer  | Owns                                                          | Example                                                 |
| ------ | ------------------------------------------------------------- | ------------------------------------------------------- |
| Base   | Global settings, phase order, concurrency, failure boundaries | `lefthook.base.yaml`                                    |
| Preset | A short, explicit list of checks                              | `lefthook.common.yaml`, `lefthook.go.yaml`              |
| Check  | One selectable job and its file selection                     | `lefthook/actionlint.yaml`, `lefthook/ruff-format.yaml` |

The existing `lefthook.<profile>.yaml` entrypoints are presets. Each extends small files under `lefthook/`. Helpers remain under `.lefthook/`; configuration and implementation are separate.

`lefthook.common.yaml` loads the base once and selects baseline checks. Other presets are additive and do not load the base. For a custom selection without common, load `lefthook.base.yaml` first.

Use one composition path for each check. In local `extends` trees, Lefthook rejects the same file reached twice, including a preset plus one of its checks. Customize an included check by job name instead of extending its file again. Presets stay at the repository root because remote extensions resolve from the selected entrypoint's directory. Check files contain no further extensions.

## Remote use

A consuming repository can use `.config/lefthook.yaml`:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.common.yaml
      - lefthook.go.yaml
      - lefthook.github.yaml
```

Replace `vX.Y.Z` with an existing release tag and protect release tags against mutation. Lefthook 2.1.15 uses `git clone --branch` for an initial remote fetch, so a raw commit SHA does not work as a cold-cache remote `ref`. A failed fetch can produce a warning while installation succeeds; inspect the merged configuration after installation.

For a smaller custom selection:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.base.yaml
      - lefthook/yamlfmt.yaml
      - lefthook/yamllint.yaml
      - lefthook/actionlint.yaml
      - lefthook/zizmor.yaml
```

Install tools through Mise, then install and inspect the hooks:

```bash
mise install
mise x -- lefthook install
mise x -- lefthook validate
mise x -- lefthook dump
```

## Presets and optional policies

| Preset                     | Checks                                                                                                                           |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `lefthook.common.yaml`     | General formatting, YAML/Shell/Markdown linting, strict JSON, repository invariants, staged secrets, Mise formatting and locking |
| `lefthook.javascript.yaml` | JavaScript/TypeScript formatting and Oxlint                                                                                      |
| `lefthook.astro.yaml`      | Astro formatting, project checks, and build                                                                                      |
| `lefthook.python.yaml`     | Ruff fixes, formatting, and linting                                                                                              |
| `lefthook.django.yaml`     | Django template formatting and linting                                                                                           |
| `lefthook.go.yaml`         | Go imports/formatting, GolangCI-Lint, module metadata, tests, vulnerabilities                                                    |
| `lefthook.container.yaml`  | Hadolint and Trivy for Dockerfiles                                                                                               |
| `lefthook.github.yaml`     | Actionlint and Zizmor                                                                                                            |
| `lefthook.helm.yaml`       | Helm documentation and linting                                                                                                   |
| `lefthook.opentofu.yaml`   | Formatting, documentation, provider locks, TFLint, Trivy, validation                                                             |
| `lefthook.terragrunt.yaml` | Formatting, provider locks, configuration and input validation                                                                   |
| `lefthook.poetry.yaml`     | Poetry configuration/lock validation and Pylint                                                                                  |
| `lefthook.renovate.yaml`   | Renovate configuration validation                                                                                                |
| `lefthook.devskim.yaml`    | DevSkim when `.devskim.json` exists                                                                                              |

CSpell, Commitlint, and signed-commit checks are opt-in. Select the desired files explicitly alongside a preset or custom base:

| Check file                        | Hook         | Purpose                                |
| --------------------------------- | ------------ | -------------------------------------- |
| `lefthook/cspell.yaml`            | `pre-commit` | Spelling for selected text files       |
| `lefthook/cspell-repository.yaml` | `pre-push`   | Spelling for the tracked repository    |
| `lefthook/commitlint.yaml`        | `commit-msg` | Conventional commit messages           |
| `lefthook/signed-commits.yaml`    | `pre-push`   | Signature presence on outgoing commits |

EditorConfig remains an editor convention. There is no EditorConfig enforcement hook. Server-side rules remain authoritative for commit-signature policy.

Every check file is independently selectable. For example, `goimports.yaml` and `gofmt.yaml`, `ruff-fix.yaml` and `ruff-format.yaml`, or `mise-format.yaml` and `mise-lock.yaml` can be chosen separately.

## Execution and overrides

Pre-commit uses named phases in a fixed order: **format → generate → validate**, retaining the current baseline's order. Mutating phases run sequentially; validation runs in parallel. A failed phase prevents later phases from running. The base has skipped empty groups; selecting a check enables its phase, so base-only and lint-only selections are valid.

Nested groups retain their order: Ruff fixes precede Ruff formatting, and Go imports precede Go formatting when their presets are selected. Unsupported job `priority` fields are removed. Phase order comes from the base and named-job merging.

The consuming repository's primary configuration can override a shared job by name. For example:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.common.yaml
      - lefthook.github.yaml
pre-commit:
  jobs:
    - name: validate
      group:
        jobs:
          - name: zizmor
            skip: true
```

Change properties such as `exclude`, `env`, or `run` through the same named path. Match the full group nesting shown by `lefthook dump`. Use `.config/lefthook-local.yaml` for personal overrides; keep team policy in the tracked primary configuration.

Existing configuration-existence gates remain in language checks. Install their tools and project dependencies and inspect the merged configuration when customizing checks.

## GitHub CI

Jobs tagged `ci` support tracked files in a clean checkout. Reuse them after installing the project's tools and fetching remote configuration:

```bash
mise install --locked
mise x -- lefthook install
mise x -- lefthook dump
mise x -- lefthook run pre-commit \
  --tag ci \
  --all-files \
  --no-stage-fixed \
  --fail-on-changes \
  --no-auto-install \
  --no-tty
```

`--all-files` replaces staged-file templates with tracked files; globs, exclusions, and file types still apply. Formatters can change the checkout. `--fail-on-changes` makes those changes fail CI, and `--no-stage-fixed` keeps formatter changes out of the index.

The tag covers file-based formatting/linting, strict JSON, path portability, symlink safety, and Gitlink metadata. It excludes staged-diff checks, newly added file checks, staged secret scanning, generators that explicitly stage output, and commit/push checks. GolangCI-Lint's staged-patch job also stays outside this tag. Run full tests, builds, repository-wide vulnerability/secret scans, and deployment checks through their appropriate CI commands.

`--no-stage-fixed` does not disable a helper's explicit `git add`. Keep generation jobs outside this generic CI command. Tags select existing jobs; they do not create a separate hook or relocate scripts. An unknown tag can select no jobs, so a CI integration should assert that its intended job names appear in `lefthook dump --format json`.

The repository's `Lefthook composition` workflow runs the native fixture suite on pull requests and main. Consumers should additionally run their selected `ci` checks.

## Mise and helpers

Use `.config/mise.toml` for a consuming repository's tool manifest. Mise owns tool versions, installation, and lockfiles. Current common tool definitions live under `.mise/config.toml` and `.mise/conf.d/`; tool-manifest redesign is a separate change.

Mise formatting and locking recognize `.config/mise.toml`, the existing `.mise/` and `.config/mise/` layouts, and root Mise files. Lock generation preserves unstaged lockfile edits and stages generated lockfiles at those locations. General TOML formatting excludes Mise configuration.

| Layer            | Responsibility                                          |
| ---------------- | ------------------------------------------------------- |
| Git              | Index, refs, ignore rules, attributes, staged blobs     |
| Mise             | Toolchain versions and installation                     |
| Lefthook         | Check selection, file selection, scheduling, staging    |
| Formatter/linter | Language and tool policy                                |
| Helper           | Structured repository checks or configuration discovery |

Simple tools run directly through `run: mise x -- ...`. Bash wrappers provide shared defaults for Commitlint, CSpell, Oxfmt, ShellCheck, yamlfmt, yamllint, Markdownlint, and Betterleaks. Repository configuration takes precedence where supported. The GitHub wrappers currently use common's Actionlint and Zizmor configuration.

Structured Git checks use Python and invoke Git for authoritative state. Hook entrypoints stay under `.lefthook/<hook-name>/`, with shared implementations under `.lefthook/lib/`. This preserves native remote script resolution.

A future Go helper can replace structured checks and repeated discovery logic while preserving check files and job names. Mise would install its release binary and upstream tools; Lefthook would call it through `mise x --`. The helper should expose explicit staged/repository modes, preserve arguments and exit codes, and invoke tools from Mise's PATH. Versions, installation, scheduling, and file selection continue to belong to their existing layers.

## Migration and verification

Consumers can keep selecting `lefthook.common.yaml` and additive profiles. Add optional policy files explicitly when upgrading if their checks are desired. For a custom selection, load the base once and choose check files. Review existing overrides against the merged configuration.

Verify that intended jobs appear after installation. Lefthook can tolerate a missing remote file, so `lefthook validate` alone does not establish that all requested checks loaded.

Run the fixture suite with the selected toolchain:

```bash
mise install python aqua:evilmartians/lefthook
mise x -- python -m unittest discover -s tests -v
```

Tests use real Lefthook in temporary Git repositories. They verify every module and preset, empty phases, remote script resolution, named overrides, order, failure propagation, partial staging, committed-file CI checks, and formatting failures without staging. A small Mise shim runs helpers, and layout tests substitute lock generation; these validate orchestration rather than Mise installation or resolution.

Upstream references:

- [Lefthook configuration](https://lefthook.dev/configuration/)
- [Remote configurations](https://lefthook.dev/configuration/remotes/)
- [Extending configuration](https://lefthook.dev/configuration/extends/)
- [Mise configuration](https://mise.jdx.dev/configuration.html)
- [Mise lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html)
