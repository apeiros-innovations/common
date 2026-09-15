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

Copy `.mise/config.toml` and these tool fragments into the consuming repository:

- `.mise/conf.d/base.toml`
- `.mise/conf.d/yamlfmt.toml`
- `.mise/conf.d/yamllint.toml`
- `.mise/conf.d/cspell.toml`

Then run:

```bash
mise install
mise lock
lefthook install
lefthook validate
lefthook dump
```

Commit the selected configuration and the resulting Mise lockfile. Lefthook downloads the remote hooks and their helpers; it does not install tools from the remote repository. Copy only the desired Mise fragments, since Mise loads all fragments present in a project's `conf.d` directory.

Remove `lefthook/cspell.yaml` and `cspell.toml` when spelling is unwanted. Keeping a CSpell config for editor use does not enable a Git hook.

## Modules and presets

`lefthook.base.yaml` establishes the execution phases and requires Lefthook 2.1.12 or newer. Include it **once, first**, before modules and presets. Always include the matching `base.toml` tool fragment.

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

The matching tool fragments are `base.toml`, `common.toml`, `go.toml`, `cspell.toml`, `commitlint.toml`, and `repository.toml` under `.mise/conf.d/`. The repository fragment supplies Python for Git-policy helpers; `common.toml` already includes that runtime.

A preset inside this repository is ordinary Lefthook configuration:

```yaml
---
extends:
  - lefthook/yamlfmt.yaml
  - lefthook/yamllint.yaml
```

For local use within this repository, see [`.lefthook.yaml`](.lefthook.yaml). To vendor the configurations elsewhere, preserve paths relative to the consumer's root and copy `.lefthook/` plus the shared tool configuration and dictionary assets needed by the selected helpers.

### Available checks

Module paths below are relative to `lefthook/`; tool fragments are relative to `.mise/conf.d/`. Several modules can use the same tool fragment. Project-owned dependencies, such as Astro, Prettier's Astro plugin, and Pylint, must be installed by the project's package manager.

| Module                      | When                                                    | Tool fragment                |
| --------------------------- | ------------------------------------------------------- | ---------------------------- |
| `just.yaml`                 | `pre-commit`                                            | `just.toml`                  |
| `mise.yaml`                 | `pre-commit`                                            | Git / Mise already available |
| `oxfmt-json.yaml`           | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxfmt-markdown.yaml`       | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxfmt-css.yaml`            | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxfmt-html.yaml`           | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxfmt-graphql.yaml`        | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxfmt-toml.yaml`           | `pre-commit`                                            | `oxfmt.toml`                 |
| `yamlfmt.yaml`              | `pre-commit`                                            | `yamlfmt.toml`               |
| `shfmt.yaml`                | `pre-commit`                                            | `shfmt.toml`                 |
| `text-hygiene.yaml`         | `pre-commit`                                            | `repository.toml`            |
| `shebang-permissions.yaml`  | `pre-commit`                                            | `repository.toml`            |
| `git-diff.yaml`             | `pre-commit`                                            | Git / Mise already available |
| `path-portability.yaml`     | `pre-commit`                                            | `repository.toml`            |
| `check-json.yaml`           | `pre-commit`                                            | `repository.toml`            |
| `yamllint.yaml`             | `pre-commit`                                            | `yamllint.toml`              |
| `shellcheck.yaml`           | `pre-commit`                                            | `shellcheck.toml`            |
| `dotenv.yaml`               | `pre-commit`                                            | `dotenv.toml`                |
| `cspell.yaml`               | `pre-commit`                                            | `cspell.toml`                |
| `markdownlint.yaml`         | `pre-commit`                                            | `markdownlint.toml`          |
| `large-files.yaml`          | `pre-commit`                                            | `repository.toml`            |
| `symlinks.yaml`             | `pre-commit`                                            | `repository.toml`            |
| `gitlinks.yaml`             | `pre-commit`                                            | `repository.toml`            |
| `forced-ignored-files.yaml` | `pre-commit`                                            | `repository.toml`            |
| `betterleaks.yaml`          | `pre-commit`                                            | `betterleaks.toml`           |
| `commitlint.yaml`           | `commit-msg`                                            | `commitlint.toml`            |
| `signed-commits.yaml`       | `pre-push`                                              | `repository.toml`            |
| `cspell-repository.yaml`    | `pre-push`                                              | `cspell.toml`                |
| `go-format.yaml`            | `pre-commit`                                            | `go-format.toml`             |
| `golangci-lint.yaml`        | `pre-commit`                                            | `golangci-lint.toml`         |
| `go-mod.yaml`               | `pre-push`                                              | `go-runtime.toml`            |
| `go-test.yaml`              | `pre-push`                                              | `go-runtime.toml`            |
| `govulncheck.yaml`          | `pre-push`                                              | `govulncheck.toml`           |
| `ruff.yaml`                 | `pre-commit`                                            | `ruff-tools.toml`            |
| `oxfmt-javascript.yaml`     | `pre-commit`                                            | `oxfmt.toml`                 |
| `oxlint.yaml`               | `pre-commit`                                            | `oxlint.toml`                |
| `astro-format.yaml`         | `pre-commit`                                            | `pnpm.toml`                  |
| `astro-check.yaml`          | `pre-push`                                              | `pnpm.toml`                  |
| `astro-build.yaml`          | `pre-push`                                              | `pnpm.toml`                  |
| `actionlint.yaml`           | `pre-commit`                                            | `actionlint.toml`            |
| `zizmor.yaml`               | `pre-commit`                                            | `zizmor.toml`                |
| `hadolint.yaml`             | `pre-commit`                                            | `hadolint.toml`              |
| `trivy-dockerfile.yaml`     | `pre-commit`                                            | `trivy.toml`                 |
| `helm-docs.yaml`            | `pre-commit`                                            | `helm-docs.toml`             |
| `helm-lint.yaml`            | `pre-commit`                                            | `helm-lint.toml`             |
| `opentofu-fmt.yaml`         | `pre-commit`                                            | `opentofu-runtime.toml`      |
| `terraform-docs.yaml`       | `pre-commit`                                            | `terraform-docs.toml`        |
| `opentofu-lock.yaml`        | `pre-commit`                                            | `opentofu-runtime.toml`      |
| `tflint.yaml`               | `pre-commit`                                            | `tflint.toml`                |
| `trivy-opentofu.yaml`       | `pre-commit`                                            | `trivy.toml`                 |
| `opentofu-validate.yaml`    | `pre-commit`                                            | `opentofu-runtime.toml`      |
| `terragrunt-fmt.yaml`       | `pre-commit`                                            | `terragrunt.toml`            |
| `terragrunt-lock.yaml`      | `pre-commit`                                            | `terragrunt.toml`            |
| `terragrunt-validate.yaml`  | `pre-commit`                                            | `terragrunt.toml`            |
| `djlint.yaml`               | `pre-commit`                                            | `djlint.toml`                |
| `poetry-check.yaml`         | `pre-commit`                                            | `poetry.toml`                |
| `pylint.yaml`               | `pre-commit`                                            | `poetry.toml`                |
| `devskim.yaml`              | `pre-commit`                                            | `devskim.toml`               |
| `renovate.yaml`             | `pre-commit`                                            | `renovate.toml`              |
| `dependencies.yaml`         | `pre-commit`, `dependency-scan`, `dependency-remediate` | `dependencies.toml`          |
| `osv.yaml`                  | `pre-commit`, `osv-scan`, `osv-remediate-npm`           | `osv.toml`                   |

The `common` preset contains general formatting, repository hygiene, YAML/Shell/Markdown linting, and Betterleaks. It excludes CSpell, Commitlint, signed-commit enforcement, and EditorConfig checking. Each remaining preset lists its component modules in the corresponding root configuration file.

`cspell.yaml` checks staged text. `cspell-repository.yaml` independently adds a pre-push scan of Git-tracked text files. Neither selection requires the other.

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

1. Add `lefthook.base.yaml` first and copy `base.toml`.
2. Keep desired presets or replace them with individual modules.
3. Explicitly select `cspell.yaml`, `commitlint.yaml`, or `signed-commits.yaml` if those policies are wanted. Add `cspell-repository.yaml` only when a full push scan is wanted.
4. Copy the corresponding Mise fragments. Remove unused CSpell, Commitlint, and EditorConfig checker pins from an old `common.toml`; `.editorconfig` itself can remain.
5. Remove redundant tool-config existence gates. Selected tools now run with defaults or report missing prerequisites.
6. Update overrides to the named phases. Generators now precede formatters, and Terragrunt's unsupported job `priority` fields are gone.
7. Regenerate the consumer's Mise lockfile, run `lefthook install`, inspect `lefthook dump`, and validate the selected checks before committing.

Keep consumers pinned to their existing release until this migration is intentional. Mise continues to recognize `.mise` and `.config/mise` layouts; the Mise hook now matches both, plus root configuration and lockfiles.

## Verify changes to common

The tests require Python 3.14, Lefthook 2.1.12, and CSpell 10.2.1, matching the tool fragments. Install only those tools for the regression suite:

```bash
mise install python node aqua:evilmartians/lefthook npm:cspell
MISE_AUTO_INSTALL=false mise x -- python -m unittest discover -s tests -v
```

Tests use real Lefthook and CSpell binaries in temporary Git repositories. They cover every module and preset, composition, remote script resolution, local overrides, phase ordering and failure propagation, partial staging, generated output, CSpell discovery, literal filenames, and tracked-only push scans. Generator tools are substituted only when testing their orchestration and staging contracts; these tests do not claim to validate a Terraform or Helm deployment.

CI runs the same suite with the pinned toolchain. For a consuming project, `lefthook validate` checks configuration and `lefthook dump` shows the assembled result. See the [Lefthook usage documentation](https://lefthook.dev/usage/) for selecting jobs, tags, and files.
