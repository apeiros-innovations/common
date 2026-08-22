# Apeiros Common

Shared development-tooling policy for Apeiros repositories.

> [!warning]
> This project is still very experimental. Changes are being made rapidly.

This repository provides:

- reusable [Lefthook](https://lefthook.dev/) configurations;
- matching [Mise](https://mise.jdx.dev/) tool definitions;
- shared formatter, linter, security, and repository-policy configuration;
- small hook helpers for checks that are not provided directly by Git or an existing tool.

This README documents the conventions specific to this repository. For Lefthook or Mise behavior, configuration syntax, and CLI usage, use the upstream documentation.

## Design

Tool ownership is intentionally separated:

| Layer                | Owns                                                                       |
| -------------------- | -------------------------------------------------------------------------- |
| Git                  | index, refs, object metadata, ignore rules, attributes, staged-diff checks |
| `.gitattributes`     | Git text and line-ending behavior                                          |
| `.gitignore`         | repository ignore policy                                                   |
| EditorConfig         | editor-facing file conventions                                             |
| Mise                 | runtimes, tool versions, lockfiles, installation                           |
| Lefthook             | hook composition, file selection, execution order                          |
| Hook helpers         | repository invariants that require structured logic                        |
| Tool-specific config | formatter, linter, spelling, and security policy                           |

Hook helpers should use Git directly when Git already exposes the required state. They should not reimplement Git semantics.

Bash is used for thin wrappers around external tools. Python is used for structured repository-policy checks.

## Profiles

`common` is the mandatory baseline. Other profiles are additive.

A Lefthook profile and its corresponding Mise fragment should be selected together.

| Profile    | Lefthook configuration     | Mise fragment                  | Purpose                                                                                       |
| ---------- | -------------------------- | ------------------------------ | --------------------------------------------------------------------------------------------- |
| Common     | `lefthook.common.yaml`     | `.mise/conf.d/common.toml`     | Baseline formatting, validation, repository policy, commit policy, spelling, secrets scanning |
| JavaScript | `lefthook.javascript.yaml` | `.mise/conf.d/javascript.toml` | JavaScript and TypeScript linting                                                             |
| Astro      | `lefthook.astro.yaml`      | `.mise/conf.d/astro.toml`      | Astro project checks and package-manager tooling                                              |
| Python     | `lefthook.python.yaml`     | `.mise/conf.d/python.toml`     | Python formatting, linting, upgrade checks, tests                                             |
| Django     | `lefthook.django.yaml`     | `.mise/conf.d/django.toml`     | Django-specific template checks                                                               |
| Go         | `lefthook.go.yaml`         | `.mise/conf.d/go.toml`         | Go formatting, linting, tests, module checks, vulnerability scanning                          |
| Container  | `lefthook.container.yaml`  | `.mise/conf.d/container.toml`  | Dockerfile linting and container/configuration security scanning                              |
| GitHub     | `lefthook.github.yaml`     | `.mise/conf.d/github.toml`     | GitHub Actions validation and security analysis                                               |
| Helm       | `lefthook.helm.yaml`       | `.mise/conf.d/helm.toml`       | Helm linting, rendering checks, and documentation                                             |
| Renovate   | `lefthook.renovate.yaml`   | `.mise/conf.d/renovate.toml`   | Renovate configuration validation                                                             |
| DevSkim    | `lefthook.devskim.yaml`    | `.mise/conf.d/devskim.toml`    | Optional DevSkim SAST when `.devskim.json` is present                                         |

## Common hooks

### Commit message

| Hook       | Implementation                    | Purpose                                                                                                                    |
| ---------- | --------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Commitlint | `.lefthook/commit-msg/commitlint` | Validates commit messages. Uses repository Commitlint configuration when present; otherwise uses the shared configuration. |

### Pre-commit

| Hook                     | Implementation                                       | Purpose                                                                                                                                         |
| ------------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Just formatting          | Lefthook command                                     | Runs `just --fmt` for staged Justfiles.                                                                                                         |
| Mise formatting          | Lefthook command                                     | Formats Mise configuration.                                                                                                                     |
| Mise lock                | Lefthook command                                     | Updates the Mise lockfile when Mise configuration changes.                                                                                      |
| Oxfmt                    | `.lefthook/pre-commit/oxfmt`                         | Formats supported JSON, Markdown, CSS, HTML, GraphQL, and TOML files.                                                                           |
| YAML formatting          | `.lefthook/pre-commit/yamlfmt`                       | Formats YAML using repository configuration when present or the shared default.                                                                 |
| Shell formatting         | Lefthook command                                     | Formats shell scripts with `shfmt`.                                                                                                             |
| Text hygiene             | `.lefthook/pre-commit/text-hygiene.py`               | Removes trailing whitespace and normalizes the final newline for files not owned by another formatter.                                          |
| Shebang permissions      | `.lefthook/pre-commit/shebang-permissions.py`        | Ensures staged shebang scripts are executable and rejects executable text files without a shebang.                                              |
| Git diff check           | Lefthook command                                     | Uses `git diff --cached --check` for Git-native whitespace and conflict-marker validation.                                                      |
| Path portability         | `.lefthook/pre-commit/check-path-portability.py`     | Rejects case/Unicode path collisions and path components that are not portable across supported developer platforms.                            |
| JSON validation          | `.lefthook/pre-commit/check-json.py`                 | Performs strict JSON parsing, including duplicate-key and non-standard constant detection.                                                      |
| YAML linting             | `.lefthook/pre-commit/yamllint`                      | Lints YAML using repository configuration when present or the shared default.                                                                   |
| ShellCheck               | `.lefthook/pre-commit/shellcheck`                    | Lints shell scripts using repository configuration when present or the shared default.                                                          |
| dotenv-linter            | Lefthook command                                     | Validates staged `.env` files.                                                                                                                  |
| CSpell                   | `.lefthook/pre-commit/cspell`                        | Spell-checks staged text files through the shared CSpell implementation.                                                                        |
| EditorConfig             | Lefthook command                                     | Validates tracked text files when the consuming repository contains an `.editorconfig`.                                                         |
| Markdownlint             | `.lefthook/pre-commit/markdownlint`                  | Lints Markdown using the shared baseline configuration.                                                                                         |
| Large-file guard         | `.lefthook/pre-commit/check-large-files.py`          | Rejects newly added staged Git blobs larger than 5 MiB. Correctly filtered Git LFS pointers pass naturally because the staged pointer is small. |
| Symlink safety           | `.lefthook/pre-commit/check-symlinks.py`             | Rejects staged symlinks whose target is absolute or escapes the repository.                                                                     |
| Gitlink validation       | `.lefthook/pre-commit/check-gitlinks.py`             | Detects accidental Gitlinks and validates staged submodule paths against staged `.gitmodules`.                                                  |
| Forced-ignore validation | `.lefthook/pre-commit/check-forced-ignored-files.py` | Rejects newly added files that were force-added despite a tracked `.gitignore` rule.                                                            |
| Betterleaks              | `.lefthook/pre-commit/betterleaks`                   | Scans staged content for secrets using repository configuration when present or the shared default.                                             |
| DevSkim                  | `.lefthook/pre-commit/devskim`                       | Runs DevSkim against staged supported source files when the DevSkim profile is enabled and `.devskim.json` exists.                              |

### Pre-push

| Hook                    | Implementation                               | Purpose                                                                                                                        |
| ----------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Signed commits          | `.lefthook/pre-push/check-signed-commits.py` | Rejects outgoing branch commits that do not contain a Git commit signature. Server-side repository rules remain authoritative. |
| CSpell repository       | `.lefthook/pre-push/cspell`                  | Spell-checks Git-tracked repository files using the shared CSpell implementation.                                              |
| EditorConfig repository | Lefthook command                             | Runs repository-wide EditorConfig validation when `.editorconfig` is tracked.                                                  |

## Hook script layout

Lefthook resolves `script:` entries relative to the Git hook that invokes them:

```text
script: cspell under pre-commit
→ .lefthook/pre-commit/cspell

script: cspell under pre-push
→ .lefthook/pre-push/cspell
```

Shared implementation belongs under `.lefthook/lib/`.

For example:

```text
.lefthook/
├── lib/
│   └── cspell
├── pre-commit/
│   └── cspell
└── pre-push/
    └── cspell
```

The hook-specific files are entrypoints. `.lefthook/lib/cspell` contains the shared implementation.

See the Lefthook documentation for script and `source_dir` behavior:

- <https://lefthook.dev/configuration/Scripts/>
- <https://lefthook.dev/configuration/source_dir/>

## Configuration precedence

Where a tool supports repository-specific configuration, the consuming repository owns its policy.

The general rule is:

```text
repository configuration exists
→ use repository configuration

repository configuration does not exist
→ use the shared configuration from common
```

This applies to the shared wrappers for tools such as Commitlint, CSpell, Oxfmt, ShellCheck, yamlfmt, yamllint, and Betterleaks.

EditorConfig is intentionally different. The common repository does not impose its `.editorconfig` remotely; EditorConfig checks run only when the consuming repository tracks its own `.editorconfig`.

DevSkim checks run only when the DevSkim profile is selected and `.devskim.json` exists.

## Mise

Mise owns the development toolchain. Lefthook configurations should not pin tool versions or bootstrap tools themselves.

The repository layout is:

```text
.mise/
├── config.toml
├── mise.lock
└── conf.d/
    ├── astro.toml
    ├── common.toml
    ├── container.toml
    ├── devskim.toml
    ├── django.toml
    ├── github.toml
    ├── go.toml
    ├── helm.toml
    ├── javascript.toml
    ├── python.toml
    └── renovate.toml
```

`common.toml` provides tools required by `lefthook.common.yaml`. Additional fragments provide the tools required by their matching Lefthook profile.

Consuming repositories copy the required Mise files into the repository. The common Mise configuration is not remotely executed by Lefthook.

For Mise configuration loading, settings, lockfiles, and CLI behavior, use the upstream documentation:

- <https://mise.jdx.dev/configuration.html>
- <https://mise.jdx.dev/configuration/settings.html>
- <https://mise.jdx.dev/dev-tools/mise-lock.html>

## Lefthook

Consuming repositories use Lefthook remote configuration to select the required profiles.

Example:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.common.yaml
      - lefthook.go.yaml
      - lefthook.container.yaml
```

Pin `ref` to the intended common release rather than tracking `main`.

The matching Mise files for the example are:

```text
.mise/config.toml
.mise/conf.d/common.toml
.mise/conf.d/go.toml
.mise/conf.d/container.toml
```

After changing the selected Mise profiles, regenerate and commit the appropriate Mise lockfile.

For remote configuration, merge behavior, jobs, groups, scripts, tags, file selection, and hook-specific behavior, use the upstream Lefthook documentation:

- <https://lefthook.dev/>
- <https://lefthook.dev/configuration/remotes/>
- <https://lefthook.dev/configuration/Scripts/>

## Bootstrap

For a newly configured repository:

```bash
mise install
lefthook install
```

Validate Lefthook configuration with:

```bash
lefthook validate
```

Inspect the fully merged Lefthook configuration with:

```bash
lefthook dump
```

For locked CI/toolchain installation:

```bash
mise install --locked
```

Where provenance re-verification is required:

```bash
MISE_LOCKED_VERIFY_PROVENANCE=1 mise install --locked
```

Refer to the Mise lockfile documentation for lockfile and provenance semantics rather than duplicating that behavior here.

## Repository policy boundaries

Do not add custom hooks where an existing layer already owns the behavior.

| Requirement                                      | Owner                       |
| ------------------------------------------------ | --------------------------- |
| Git line-ending and text attributes              | `.gitattributes`            |
| Ignore rules                                     | `.gitignore`                |
| Staged whitespace/conflict-marker validation     | `git diff --cached --check` |
| Editor behavior                                  | `.editorconfig`             |
| Tool installation/version resolution             | Mise                        |
| Hook lifecycle and file selection                | Lefthook                    |
| Language formatting/linting                      | Existing formatter/linter   |
| Repository invariants requiring structured logic | Python hook helper          |

New shared hooks should prevent a distinct class of failure and should not duplicate an existing tool.
