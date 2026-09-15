# Apeiros Common

Composable development checks for Git repositories, using [Lefthook](https://lefthook.dev/) and [Mise](https://mise.jdx.dev/).

Select the checks a project needs. A tool configuration customizes an enabled check; its presence does not enable or disable that check. No project CSpell configuration is required. EditorConfig remains an editor preference and is not checked by these hooks.

> [!WARNING]
> This project is experimental. Pin consumers to a release and review the migration notes before updating.

## Start with selected checks

This example enables YAML formatting, YAML linting, and staged spelling checks:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z # Replace with the intended release.
    configs:
      - lefthook.base.yaml
      - lefthook/yamlfmt.yaml
      - lefthook/yamllint.yaml
      - lefthook/cspell.yaml
```

Copy `.mise/config.toml` from the same release into the consumer, or merge its settings and tasks into an existing file. Bootstrap the generator once:

```bash
mise --no-hooks x python@3.14.7 aqua:evilmartians/lefthook@2.1.12 -- lefthook run common-tools
mise install
mise lock
lefthook validate
lefthook dump
```

Lefthook installs the remote hooks automatically on the first run. The `common-tools` command uses the catalog and generator from that same remote release to write `.mise/conf.d/common.toml`. It includes only the selected checks' requirements plus Python and Lefthook for the generator. No tool fragments need to be selected or copied.

Commit `.lefthook.yaml`, `.mise/config.toml`, the generated `.mise/conf.d/common.toml`, and `.mise/mise.lock`. Subsequent developers run `mise install`; the configured postinstall hook installs Lefthook's Git hooks. They do not need to regenerate configuration to start working.

To change the checks or update the shared release:

```bash
mise run tools:sync
mise install
mise lock
mise run tools:check
```

Remove `lefthook/cspell.yaml` from the selection and sync again when spelling is unwanted. Keeping a CSpell config for editor use does not enable a Git hook. If the repository-wide spelling module is still selected, CSpell remains a required tool.

## Modules and presets

`lefthook.base.yaml` establishes the execution phases and requires Lefthook 2.1.12 or newer. Include it **once, first**, before modules and presets. It also exposes the manual `common-tools` synchronization command; this is not a Git event.

Individual modules live in `lefthook/`. The existing `lefthook.<profile>.yaml` files are optional presets containing only `extends` lists. Presets do not include the base or other presets, so several presets can be composed without repeated base imports.

For example:

```yaml
---
remotes:
  - git_url: https://github.com/apeiros-innovations/common.git
    ref: vX.Y.Z
    configs:
      - lefthook.base.yaml
      - lefthook.common.yaml
      - lefthook.go.yaml
      - lefthook/cspell.yaml
      - lefthook/commitlint.yaml
      - lefthook/signed-commits.yaml
```

Run `mise run tools:sync` after changing this selection. The generated `common.toml` includes the combined requirements, with each tool declared once. Its filename does not imply selection of the `common` hook preset.

A preset inside this repository is ordinary Lefthook configuration:

```yaml
---
extends:
  - lefthook/yamlfmt.yaml
  - lefthook/yamllint.yaml
```

For local use within this repository, see [`.lefthook.yaml`](.lefthook.yaml). To vendor the configurations elsewhere, preserve paths relative to the consumer's root and copy `.lefthook/`, `tools/catalog.toml`, and the shared tool configuration and dictionary assets needed by the selected helpers. Keep local extension paths within the consuming repository.

### Available checks

Module paths below are relative to `lefthook/`. Tool groups are declared in `tools/catalog.toml` and selected automatically by the modules; consumers do not maintain a separate group list. Project-owned dependencies, such as Astro, Prettier's Astro plugin, and Pylint, must be installed by the project's package manager.

| Module                      | When                                                    | Tool group         |
| --------------------------- | ------------------------------------------------------- | ------------------ |
| `just.yaml`                 | `pre-commit`                                            | `just`             |
| `mise.yaml`                 | `pre-commit`                                            | `system`           |
| `oxfmt-json.yaml`           | `pre-commit`                                            | `oxfmt`            |
| `oxfmt-markdown.yaml`       | `pre-commit`                                            | `oxfmt`            |
| `oxfmt-css.yaml`            | `pre-commit`                                            | `oxfmt`            |
| `oxfmt-html.yaml`           | `pre-commit`                                            | `oxfmt`            |
| `oxfmt-graphql.yaml`        | `pre-commit`                                            | `oxfmt`            |
| `oxfmt-toml.yaml`           | `pre-commit`                                            | `oxfmt`            |
| `yamlfmt.yaml`              | `pre-commit`                                            | `yamlfmt`          |
| `shfmt.yaml`                | `pre-commit`                                            | `shfmt`            |
| `text-hygiene.yaml`         | `pre-commit`                                            | `repository`       |
| `shebang-permissions.yaml`  | `pre-commit`                                            | `repository`       |
| `git-diff.yaml`             | `pre-commit`                                            | `system`           |
| `path-portability.yaml`     | `pre-commit`                                            | `repository`       |
| `check-json.yaml`           | `pre-commit`                                            | `repository`       |
| `yamllint.yaml`             | `pre-commit`                                            | `yamllint`         |
| `shellcheck.yaml`           | `pre-commit`                                            | `shellcheck`       |
| `dotenv.yaml`               | `pre-commit`                                            | `dotenv`           |
| `cspell.yaml`               | `pre-commit`                                            | `cspell`           |
| `markdownlint.yaml`         | `pre-commit`                                            | `markdownlint`     |
| `large-files.yaml`          | `pre-commit`                                            | `repository`       |
| `symlinks.yaml`             | `pre-commit`                                            | `repository`       |
| `gitlinks.yaml`             | `pre-commit`                                            | `repository`       |
| `forced-ignored-files.yaml` | `pre-commit`                                            | `repository`       |
| `betterleaks.yaml`          | `pre-commit`                                            | `betterleaks`      |
| `commitlint.yaml`           | `commit-msg`                                            | `commitlint`       |
| `signed-commits.yaml`       | `pre-push`                                              | `repository`       |
| `cspell-repository.yaml`    | `pre-push`                                              | `cspell`           |
| `go-format.yaml`            | `pre-commit`                                            | `go-format`        |
| `golangci-lint.yaml`        | `pre-commit`                                            | `golangci-lint`    |
| `go-mod.yaml`               | `pre-push`                                              | `go-runtime`       |
| `go-test.yaml`              | `pre-push`                                              | `go-runtime`       |
| `govulncheck.yaml`          | `pre-push`                                              | `govulncheck`      |
| `ruff.yaml`                 | `pre-commit`                                            | `ruff`             |
| `oxfmt-javascript.yaml`     | `pre-commit`                                            | `oxfmt`            |
| `oxlint.yaml`               | `pre-commit`                                            | `oxlint`           |
| `astro-format.yaml`         | `pre-commit`                                            | `pnpm`             |
| `astro-check.yaml`          | `pre-push`                                              | `pnpm`             |
| `astro-build.yaml`          | `pre-push`                                              | `pnpm`             |
| `actionlint.yaml`           | `pre-commit`                                            | `actionlint`       |
| `zizmor.yaml`               | `pre-commit`                                            | `zizmor`           |
| `hadolint.yaml`             | `pre-commit`                                            | `hadolint`         |
| `trivy-dockerfile.yaml`     | `pre-commit`                                            | `trivy`            |
| `helm-docs.yaml`            | `pre-commit`                                            | `helm-docs`        |
| `helm-lint.yaml`            | `pre-commit`                                            | `helm-lint`        |
| `opentofu-fmt.yaml`         | `pre-commit`                                            | `opentofu-runtime` |
| `terraform-docs.yaml`       | `pre-commit`                                            | `terraform-docs`   |
| `opentofu-lock.yaml`        | `pre-commit`                                            | `opentofu-runtime` |
| `tflint.yaml`               | `pre-commit`                                            | `tflint`           |
| `trivy-opentofu.yaml`       | `pre-commit`                                            | `trivy`            |
| `opentofu-validate.yaml`    | `pre-commit`                                            | `opentofu-runtime` |
| `terragrunt-fmt.yaml`       | `pre-commit`                                            | `terragrunt`       |
| `terragrunt-lock.yaml`      | `pre-commit`                                            | `terragrunt`       |
| `terragrunt-validate.yaml`  | `pre-commit`                                            | `terragrunt`       |
| `djlint.yaml`               | `pre-commit`                                            | `djlint`           |
| `poetry-check.yaml`         | `pre-commit`                                            | `poetry`           |
| `pylint.yaml`               | `pre-commit`                                            | `poetry`           |
| `devskim.yaml`              | `pre-commit`                                            | `devskim`          |
| `renovate.yaml`             | `pre-commit`                                            | `renovate`         |
| `dependencies.yaml`         | `pre-commit`, `dependency-scan`, `dependency-remediate` | `dependencies`     |
| `osv.yaml`                  | `pre-commit`, `osv-scan`, `osv-remediate-npm`           | `osv`              |

The `common` preset contains general formatting, repository hygiene, YAML/Shell/Markdown linting, and Betterleaks. It excludes CSpell, Commitlint, signed-commit enforcement, and EditorConfig checking. Each remaining preset lists its component modules in the corresponding root configuration file.

`cspell.yaml` checks staged text. `cspell-repository.yaml` independently adds a pre-push scan of Git-tracked text files. Neither selection requires the other.

## Generated tool configuration

`tools/catalog.toml` is the single maintained source for shared tool versions. Its `[tools]` table uses Mise's tool definitions, including backend options and installation dependencies. `[groups.<name>]` lists the tools for each capability; a group can also carry its necessary `env` and `deps` settings. The catalog itself is outside Mise's automatic configuration search.

```toml
schema_version = 1

[tools]
node = "26.8.1"
"npm:cspell" = "10.2.1"

[groups.cspell]
tools = ["node", "npm:cspell"]
```

Each shared job declares a `common-tools:<group>` tag. The generator asks `lefthook dump --format json` to resolve configuration, collects those tags, and combines their requirements. Presets remain ordinary `extends` lists. It does not parse shell commands or implement Lefthook's merge rules. Unknown groups, missing tool definitions, dependency cycles, and conflicting group settings fail clearly.

| File                       | Ownership                                                     |
| -------------------------- | ------------------------------------------------------------- |
| `.lefthook.yaml`           | Project selection of modules and presets                      |
| `.mise/config.toml`        | Project tools, overrides, settings, and synchronization tasks |
| `.mise/conf.d/common.toml` | Generated requirements for the selected shared checks         |
| `.mise/mise.lock`          | Tool installations locked by Mise                             |

Project tools and intentional version overrides belong in `.mise/config.toml`, which takes precedence over the generated fragment. Other project fragments are left intact. Keep the `common-tools:` tags when overriding shared jobs; project-owned jobs can declare a known group when they need its tools. The generator only manages requirements declared by these tags.

`mise run tools:sync --check` and `mise run tools:check` both verify that generated configuration is current without modifying files. Ordinary TOML formatting is allowed. Synchronization writes only `common.toml`, removes requirements no longer selected, and refuses to overwrite a file without its generated-file marker. It neither installs tools nor changes the lockfile or Git index; run `mise install` and `mise lock` explicitly after a change.

Generation reads the current team configuration so edits can be previewed before committing. Untracked personal Lefthook override files, including ignored overrides, are excluded through a temporary directory view; the originals are never moved or edited. A deliberately tracked override participates in generation. Conditional skips, tags used to exclude execution, and the current staged-file list do not remove selected tools. Linked Git worktrees keep their own output.

Renovate is configured to update the catalog's native `[tools]` entries and leave generated pins alone. After a catalog update, run `mise run tools:sync` and `mise lock` on that branch and commit the results. CI detects stale generated output. Consumers update the pinned common release and regenerate to adopt its tool versions. This keeps version changes in the shared catalog reviewable and avoids independently updating derived pins.

## Execution and overrides

Pre-commit runs these phases in order, regardless of the order in which modules are selected after the base:

| Phase      | Execution  | Purpose                               |
| ---------- | ---------- | ------------------------------------- |
| `generate` | Sequential | Documentation and lockfile generation |
| `format`   | Sequential | Formatting and automatic fixes        |
| `validate` | Parallel   | Independent read-only checks          |

Generation runs first so output guards do not mistake a formatter's unstaged changes for existing developer edits. Mutating jobs run sequentially to avoid competing writes. The next phase runs only after the previous phase succeeds. Jobs with their own dependencies, such as goimports followed by gofmt, use a sequential `piped` group.

The base declares skipped, empty phase groups. A selected module sets `skip: false` on its populated phase. This keeps a base-only or spelling-only configuration valid: Lefthook 2.1 reports an execution error for an active empty group.

Lefthook caches the initial staged-file list and stages `stage_fixed` changes at the end of the hook. A generator therefore formats and stages its own new outputs. OpenTofu and Helm documentation generation include Oxfmt in their tool requirements. Existing unstaged output is protected by their helpers; partially staged input remains under Lefthook's native stash/restore handling.

Named jobs merge by name. Preserve phase and job names when overriding a module. Do not use `priority` on `jobs`: the pinned version supports it for legacy `commands` and `scripts` only.

Lefthook applies main configuration, `extends`, `remotes`, and finally local configuration in that order. For an override that wins over remote settings, use `.lefthook-local.yaml` when the main file is `.lefthook.yaml` (or `lefthook-local.yml` with `lefthook.yml`). For example:

```yaml
---
pre-commit:
  jobs:
    - name: validate
      group:
        jobs:
          - name: cspell
            exclude:
              - "**/*.svg"
              - "generated/**"
```

Keep personal overrides ignored. A team can deliberately track an override file, but it should document that convention. For permanent check selection, edit the selected modules or preset.

Lefthook rejects a file repeated anywhere in one nested `extends` traversal. When composing with local `extends`, do not also list a module already included by a selected preset. Module files have `extends: []` to clear a preceding remote preset's extension list when selected directly. Keep preset paths rooted at the shared repository; moving presets into subdirectories changes remote path resolution in the pinned version.

These conventions were checked against Lefthook 2.1.12's implementation and the upstream documentation:

- [Configuration precedence and extends](https://lefthook.dev/configuration/extends/)
- [Remote configurations](https://lefthook.dev/configuration/remotes/)
- [Named jobs and groups](https://lefthook.dev/configuration/jobs/)
- [Sequential failure handling](https://lefthook.dev/configuration/piped/)
- [Script locations](https://lefthook.dev/configuration/source_dir/)
- [File templates](https://lefthook.dev/configuration/run/) and [automatic staging](https://lefthook.dev/configuration/stage_fixed/)

## CSpell configuration

The selected spelling modules use the same helper for staged and repository-wide checks:

1. `CSPELL_CONFIG`, if set, selects that file and its explicit imports. Automatic discovery is disabled. A relative path is resolved from the consuming repository root; an invalid path fails with an explanation.
2. Otherwise, one project config at the root, under `.config`, under `.vscode`, or in the root `package.json` is selected. Only the top-level `cspell` setting makes `package.json` a configuration; having CSpell as a dependency does not.
3. Without a project config, the shared `.cspell.yaml` and dictionaries are used. Automatic discovery is disabled in this case, preventing an unrelated parent-directory config from changing results.

A project config owns its policy, including file selection. When one is present, native CSpell discovery supports nested configurations, imports, and overrides. Add a project root config when using nested configs. With no project config, the shared defaults apply to all checked files.

Example project customization:

```yaml
---
version: "0.2"
language: en
words:
  - Kumitate
ignorePaths:
  - generated/**
```

Multiple project root configs fail with their paths and guidance to keep one config, import additional settings, or set `CSPELL_CONFIG`. This prevents adding a word to one config while CSpell silently discovers another. The configuration itself is still checked; it is not broadly excluded to hide spelling errors.

Diagnose an allowed word with:

```bash
mise x -- cspell trace --config .cspell.yaml Kumitate
```

Run the selected staged spelling job against all tracked files without adding a push hook:

```bash
lefthook run pre-commit --job cspell --all-files
```

See [CSpell configuration](https://cspell.org/docs/Configuration) for supported formats and merging behavior. In CSpell 10.2.1, `--stop-config-search-at` does not bound per-document discovery when no project config is found; the shared fallback deliberately uses `--no-config-search`.

## Tool policy and helpers

Git owns the index, attributes, ignored files, and refs. Mise owns runtimes, tool versions, and lockfiles. Lefthook owns composition, file selection, and execution. Tool configuration owns formatting and lint policy.

The shared wrappers for Commitlint, Oxfmt, ShellCheck, yamlfmt, yamllint, Markdownlint, and Betterleaks use repository configuration when available, with shared defaults where supported. DevSkim can run with its defaults; `DEVSKIM_OPTIONS_JSON` selects an explicit options file and fails clearly if that file is missing. Selecting a module that needs project dependencies should surface missing dependencies rather than silently skipping the check.

Bash wrappers stay under `.lefthook/<git-hook>/`; common implementations are under `.lefthook/lib/`. Structured Git checks use Python. This layout preserves Lefthook's native remote script resolution.

Repository-policy modules remain independently selectable:

- Large-file checking rejects newly staged Git blobs over 5 MiB; normal Git LFS pointers pass.
- Symlink checking rejects absolute targets and targets escaping the repository.
- Gitlink checking validates staged submodule metadata.
- Forced-ignore checking catches newly force-added files covered by tracked ignore rules.
- Signature checking looks for signatures on outgoing commits; server-side rules remain authoritative.

## Migration

When upgrading a consumer from the previous profiles:

1. Add `lefthook.base.yaml` first and copy or merge `.mise/config.toml` from the selected shared release.
2. Keep desired presets or replace them with individual modules.
3. Explicitly select `cspell.yaml`, `commitlint.yaml`, or `signed-commits.yaml` if those policies are wanted. Add `cspell-repository.yaml` only when a full push scan is wanted.
4. Move any project-specific settings out of the old `common.toml` into `.mise/config.toml`, then remove the old shared tool fragments. Run the bootstrap command above to generate the new `.mise/conf.d/common.toml`. Keep unrelated project fragments. Remove any remaining EditorConfig checker pin; `.editorconfig` itself can remain.
5. Remove redundant tool-config existence gates. Selected tools now run with defaults or report missing prerequisites.
6. Update overrides to the named phases. Generators now precede formatters, and Terragrunt's unsupported job `priority` fields are gone.
7. Regenerate the consumer's Mise lockfile, run `lefthook install`, inspect `lefthook dump`, and validate the selected checks before committing.

Keep consumers pinned to their existing release until this migration is intentional. Mise continues to recognize `.mise` and `.config/mise` layouts; the Mise hook now matches both, plus root configuration and lockfiles.

## Verify changes to common

The tests require Mise 2026.8.12 or newer and the Python, Lefthook, and CSpell versions in the tool catalog. Install only those tools for the regression suite:

```bash
mise install python node aqua:evilmartians/lefthook npm:cspell
MISE_AUTO_INSTALL=false mise run tools:check
MISE_AUTO_INSTALL=false mise x -- python -m unittest discover -s tests -v
```

Tests use real Lefthook and CSpell binaries in temporary Git repositories. They cover every module and preset, composition, remote script resolution, local overrides, phase ordering and failure propagation, partial staging, generated output, CSpell discovery, literal filenames, and tracked-only push scans. Generator tools are substituted only when testing their orchestration and staging contracts; these tests do not claim to validate a Terraform or Helm deployment.

Catalog coverage also checks every module, remote release selection, deduplication, removal of unused tools, personal and tracked overrides, linked worktrees, preservation of project settings, and detection of stale output. CI verifies generated configuration and runs the same suite with the pinned toolchain. For a consuming project, `lefthook validate` checks configuration and `lefthook dump` shows the assembled result. See the [Lefthook usage documentation](https://lefthook.dev/usage/) for selecting jobs, tags, and files.
