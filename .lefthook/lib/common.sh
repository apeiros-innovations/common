#!/usr/bin/env bash

set -euo pipefail

common_remote_root() {
	local root

	root="$(
		cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." &&
			pwd -P
	)"

	printf '%s\n' "$root"
}

first_existing_file() {
	local candidate

	for candidate in "$@"; do
		if [[ -f $candidate ]]; then
			printf '%s\n' "$candidate"
			return 0
		fi
	done

	return 1
}

has_commitlint_config() {
	local candidate

	for candidate in \
		.commitlintrc \
		.commitlintrc.json \
		.commitlintrc.yaml \
		.commitlintrc.yml \
		.commitlintrc.js \
		.commitlintrc.cjs \
		.commitlintrc.mjs \
		.commitlintrc.ts \
		.commitlintrc.cts \
		.commitlintrc.mts \
		commitlint.config.js \
		commitlint.config.cjs \
		commitlint.config.mjs \
		commitlint.config.ts \
		commitlint.config.cts \
		commitlint.config.mts; do
		[[ -f $candidate ]] && return 0
	done

	if [[ -f package.json ]] &&
		grep -Eq '"commitlint"[[:space:]]*:' package.json; then
		return 0
	fi

	if [[ -f package.yaml ]] &&
		grep -Eq '^[[:space:]]*commitlint[[:space:]]*:' package.yaml; then
		return 0
	fi

	return 1
}

has_oxfmt_root_config() {
	[[ -f .oxfmtrc.json ]] ||
		[[ -f .oxfmtrc.jsonc ]] ||
		[[ -f oxfmt.config.ts ]] ||
		[[ -f oxfmt.config.mts ]]
}

has_shellcheck_config() {
	git ls-files |
		grep -Eq '(^|/)(\.shellcheckrc|shellcheckrc)$'
}

has_cspell_config() {
	git ls-files |
		grep -Eq '(^|/)(\.?cspell(\.config)?\.(yaml|yml|json|jsonc|mjs|cjs|js|mts|ts|cts|toml)|\.?cSpell\.json)$' &&
		return 0

	git ls-files |
		grep -Eq '(^|/)\.vscode/(cspell|cSpell|\.cspell)\.json$' &&
		return 0

	if [[ -f package.json ]] &&
		grep -Eq '"cspell"[[:space:]]*:' package.json; then
		return 0
	fi

	return 1
}
