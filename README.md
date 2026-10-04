# Apeiros Common

Shared development-tooling policy for Apeiros repositories.

> [!warning]
> This project is experimental. Consumers track the shared configuration on `main`.

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

A consuming repository can use `.lefthook.yaml`:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: main
    refetch_frequency: 24h
    configs:
      - lefthook.common.yaml
      - lefthook.go.yaml
      - lefthook.github.yaml
```

Keep `.lefthook.yaml` at the repository root. The remote follows the common `main` branch. `refetch_frequency: 24h` lets Lefthook refresh its cached remote during installation once the cache is at least 24 hours old. Run `mise x -- lefthook install` to install or refresh hooks, and inspect the selected checks with `mise x -- lefthook dump`.

For a smaller custom selection:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: main
    refetch_frequency: 24h
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
| `lefthook.devskim.yaml`    | DevSkim when `.devskim.json` exists or `DEVSKIM_OPTIONS_JSON` selects a configuration                                            |

CSpell, Commitlint, and signed-commit checks are opt-in. Select the desired files explicitly alongside a preset or custom base:

| Check file                        | Hook         | Purpose                                      |
| --------------------------------- | ------------ | -------------------------------------------- |
| `lefthook/cspell.yaml`            | `pre-commit` | Spelling for selected text files             |
| `lefthook/cspell-repository.yaml` | `pre-push`   | Spelling for the tracked repository          |
| `lefthook/commitlint.yaml`        | `commit-msg` | Conventional commit messages                 |
| `lefthook/signed-commits.yaml`    | `pre-push`   | Signature presence on outgoing commits       |
| `lefthook/osv-scanner.yaml`       | `pre-commit` | Vulnerabilities in selected dependency locks |

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
    ref: main
    refetch_frequency: 24h
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

Install the selected checks' tools and project dependencies and inspect the merged configuration when customizing checks.

## File selection and eligibility

Each file-based check owns its native Lefthook filters:

- `glob` selects extensions or filenames. No matching files means the job is skipped.
- `exclude` removes generated output, caches, or other unsuitable paths.
- `file_types` excludes symlinks from language tools. Text-only checks additionally select `text`; validators still receive malformed files rather than relying on MIME detection.
- `only` declares project prerequisites, such as a linter configuration or project manifest. Both the prerequisite and the file filters must pass.

`run:` jobs can use native globs even without file arguments. Script jobs pass a file template through `args:` so Lefthook applies their filters before launching the helper. Commit checks use `{staged_files}`; repository spelling uses `{all_files}`. Repository spelling scans existing tracked text files, including dotfiles, and excludes SVGs, binaries, symlinks, and untracked files.

CSpell's `only` gate recognizes existing configuration filenames in tracked or nonignored untracked paths, a `cspell` entry in root `package.json`, or inherited `CSPELL_CONFIG`. DevSkim recognizes `.devskim.json` or inherited `DEVSKIM_OPTIONS_JSON`. The helper validates explicit configuration paths, so a missing override fails once the job is eligible. Checks that support shared defaults do not universally require a local configuration file.

In Lefthook 2.1.15, `only.run` probes inherit the shell or CI environment before per-job `env` is applied. Export configuration overrides in that environment. If a named-job override instead sets a custom configuration through `env`, also set `only: true` on that job; file filters still apply and the helper validates the selected configuration.

Poetry requires `pyproject.toml` and a matching Python or dependency-file change. Astro push checks require a project manifest and use build-input globs, including `src/` and `public/`, so unrelated documentation changes skip checks and builds. Extend those globs for additional project-specific inputs. Repository-wide Go checks retain their tracked `go.mod` prerequisite and run across modules; assets and test fixtures can affect Go tests without changing a `.go` file.

OpenTofu and Terragrunt formatting run directly from their check YAML. Lefthook selects files and excludes caches; small inline loops invoke each tool once per file. Their helpers retain module discovery, validation, provider locking, and protection for unstaged edits.

Git policy checks retain index-aware selection. Checkout content filters would be inappropriate for checks of staged file modes, symlinks, Gitlinks, deleted paths, or newly added blobs.

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

## Mise and helpers

Common declares tool versions and backend options once in `.config/mise.toml`, grouped by purpose within the same file. This is common's own full tool selection. Mise owns installation and `.config/mise.lock`; native dependency graphs live under `.config/mise/locks/`. Commit lockfiles and graphs together.

Consumers keep their own `.config/mise.toml` and copy only the tools needed by their selected checks. Start with Lefthook:

```toml
#:schema https://mise.jdx.dev/schema/mise.json
min_version = { hard = "2026.8.12" }

[settings]
lockfile = true
experimental = true

[tools]
"aqua:evilmartians/lefthook" = "2.1.15"
```

Keep the [Lefthook remote configuration](#remote-use) in `.lefthook.yaml`. Add the desired blocks below inside the existing `[tools]` table. Declare each tool only once when combining blocks, and choose runtime versions compatible with the project. For an individual check, copy only its tool and dependencies from the matching block. Python is also needed for the structured Git checks, including the optional signed-commit check.

Mise installs the declared tools. Lefthook's globs and prerequisites decide when their checks run. A workflow-only project can select `lefthook.base.yaml` and `lefthook.github.yaml` and copy just the GitHub block; it needs no language runtimes or other linters.

These examples are maintained manually alongside [common's manifest](.config/mise.toml). After copying, the consuming repository owns its versions, lockfile, and dependency graphs; Renovate can update its Mise declarations independently. Upgrading the Lefthook remote does not change those tool versions.

### Tools by preset

**Common — `lefthook.common.yaml`**

```toml
python = "3.14.7"
node = "26.10.0"
"npm:oxfmt" = "0.71.0"
"npm:markdownlint-cli2" = "0.23.3"
"aqua:astral-sh/uv" = "0.12.21"
"aqua:mvdan/sh" = "3.14.1"
"aqua:casey/just" = "1.58.0"
"aqua:betterleaks/betterleaks" = "1.9.0"
"aqua:koalaman/shellcheck" = "0.11.0"
"aqua:google/yamlfmt" = "0.21.0"
"aqua:dotenv-linter/dotenv-linter" = "4.0.0"
"pipx:yamllint" = { version = "1.38.0", depends = ["python", "aqua:astral-sh/uv"] }
```

**GitHub — `lefthook.github.yaml`**

```toml
"aqua:rhysd/actionlint" = "1.7.12"
"aqua:zizmorcore/zizmor" = "1.30.1"
```

**Go — `lefthook.go.yaml`**

```toml
go = "1.27.1"
"aqua:golangci/golangci-lint" = "2.14.0"
"go:golang.org/x/tools/cmd/goimports" = "0.50.0"
"go:golang.org/x/vuln/cmd/govulncheck" = "1.8.0"
```

**Python — `lefthook.python.yaml`**

```toml
python = "3.14.7"
"aqua:astral-sh/ruff" = "0.16.9"
```

**JavaScript — `lefthook.javascript.yaml`**

```toml
node = "26.10.0"
"npm:oxfmt" = "0.71.0"
"npm:oxlint" = "1.86.0"
```

**Astro — `lefthook.astro.yaml`**

```toml
node = "26.10.0"
pnpm = "12.8.1"
```

Install Astro, Prettier, its Astro plugin, and any check dependencies in the project's package manifest; the hooks use `pnpm exec`.

**Django — `lefthook.django.yaml`**

```toml
python = "3.14.7"
"aqua:astral-sh/ruff" = "0.16.9"
"pipx:djlint" = { version = "1.46.3", depends = ["python", "aqua:astral-sh/ruff"] }
```

**Poetry — `lefthook.poetry.yaml`**

```toml
python = "3.14.7"
"aqua:astral-sh/uv" = "0.12.21"
"pipx:poetry" = { version = "2.5.1", depends = ["python", "aqua:astral-sh/uv"] }
```

Keep Pylint in the project's Poetry development dependencies when selecting its check, and install those dependencies before running hooks.

**Containers — `lefthook.container.yaml`**

```toml
"aqua:hadolint/hadolint" = "2.15.1"
"aqua:aquasecurity/trivy" = "0.74.0"
```

**Helm — `lefthook.helm.yaml`**

```toml
"aqua:helm/helm" = "4.3.0"
"aqua:norwoodj/helm-docs" = "1.14.2"
```

**OpenTofu — `lefthook.opentofu.yaml`**

```toml
"aqua:opentofu/opentofu" = "1.13.0"
"aqua:terraform-docs/terraform-docs" = "0.24.0"
"aqua:terraform-linters/tflint" = "0.64.0"
"aqua:aquasecurity/trivy" = "0.74.0"
```

**Terragrunt — `lefthook.terragrunt.yaml`**

```toml
"aqua:opentofu/opentofu" = "1.13.0"
"aqua:gruntwork-io/terragrunt" = "1.1.6"
```

**Renovate — `lefthook.renovate.yaml`**

```toml
node = "26.10.0"
"npm:renovate" = { version = "44.126.0", allow_builds = ["re2"], trust_policy_excludes = ["@yarnpkg/libzip@3.2.2"] }
```

**DevSkim — `lefthook.devskim.yaml`**

```toml
dotnet = "10.0.401"
"dotnet:Microsoft.CST.DevSkim.CLI" = { version = "1.0.100" }
```

**Optional spelling — `lefthook/cspell.yaml` and `lefthook/cspell-repository.yaml`**

```toml
node = "26.10.0"
"npm:cspell" = "10.3.6"
```

**Optional commit messages — `lefthook/commitlint.yaml`**

```toml
node = "26.10.0"
"npm:@commitlint/cli" = "21.2.3"
"npm:@commitlint/config-conventional" = "21.2.3"
```

**Optional dependency scanning — `lefthook/osv-scanner.yaml`**

```toml
"aqua:google/osv-scanner" = "2.6.0"
```

The former `lefthook.dependencies.yaml` entrypoint is replaced by this explicitly selected check.

### Installation and workflow versions

Prepare and inspect the selected hooks:

```bash
mise trust
mise install
mise lock
mise x -- lefthook install
mise x -- lefthook dump
```

CI can use `mise install --locked` for the project's selection. When a workflow action installs its own tools, read their versions directly from `.config/mise.toml`:

```bash
echo "actionlint=$(mise config get --file .config/mise.toml tools.aqua:rhysd/actionlint)" >> "$GITHUB_OUTPUT"
echo "zizmor=$(mise config get --file .config/mise.toml tools.aqua:zizmorcore/zizmor)" >> "$GITHUB_OUTPUT"
```

The [workflow lint job](.github/workflows/workflow-lint.yaml) passes those outputs to the pinned shared action. These queries do not install tools or repeat version pins in workflow YAML. For a tool declared as an options table, query its `.version` field instead.

Mise formatting and locking also recognize the legacy `.mise/` and `.config/mise/` layouts and root Mise files. Lock generation preserves unstaged edits and stages lockfiles and dependency graphs. Generated graphs are excluded from general formatting, YAML linting, and spelling so their recorded digests remain valid. Common's own local tool installation installs Git hooks when Lefthook is available; CI skips that step. Poetry creates its project environment when invoked.

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

Upstream references:

- [Lefthook configuration](https://lefthook.dev/configuration/)
- [Remote configurations](https://lefthook.dev/configuration/remotes/)
- [Extending configuration](https://lefthook.dev/configuration/extends/)
- [File globs](https://lefthook.dev/configuration/glob/)
- [File types](https://lefthook.dev/configuration/file_types/)
- [Job prerequisites](https://lefthook.dev/configuration/only/)
- [Mise configuration](https://mise.jdx.dev/configuration.html)
- [Mise lockfiles](https://mise.jdx.dev/dev-tools/mise-lock.html)
- [Mise config values](https://mise.jdx.dev/cli/config/get.html)
