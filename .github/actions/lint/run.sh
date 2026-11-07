#!/usr/bin/env bash
set -euo pipefail

# Inputs are data, never interpolated into a shell command. Reject CLI flags.
read -r -a selected_tools <<< "${LINT_TOOLS:?tools must be set}"
for tool in "${selected_tools[@]}"; do
	if [[ ! "$tool" =~ ^[a-zA-Z0-9][a-zA-Z0-9:/_.@+-]*$ ]]; then
		printf >&2 'Invalid Mise tool name: %s\n' "$tool"
		exit 1
	fi
done
tools=(node aqua:evilmartians/lefthook "${selected_tools[@]}")
export MISE_ENABLE_TOOLS
MISE_ENABLE_TOOLS=$(IFS=,; echo "${tools[*]}")

# Require exact configured keys. A short alias can resolve to a different backend
# (for example actionlint vs aqua:kjanat/actionlint) or an unrelated old lock entry.
configured_tools=$(mise ls --current --json)
for tool in "${tools[@]}"; do
	if ! jq -e --arg tool "$tool" 'has($tool)' <<< "$configured_tools" >/dev/null; then
		printf >&2 'Declare this exact tool key in Mise before using shared lint: %s\n' "$tool"
		exit 1
	fi
done

if [[ -n "${LEFTHOOK_CONFIG:-}" && ! -f "$LEFTHOOK_CONFIG" ]]; then
	printf >&2 'Lefthook configuration does not exist: %s\n' "$LEFTHOOK_CONFIG"
	exit 1
fi

mise install --locked "${tools[@]}"
mise x -- lefthook install

config_dump=$(mktemp)
trap 'rm -f "$config_dump"' EXIT
mise x -- lefthook dump --format json > "$config_dump"
mise x -- node "$LINT_ACTION_PATH/check-config.mjs" "$config_dump"

# https://lefthook.dev/usage/commands/run/
# All tracked files, the same ci tag as local runs, and no staged fixes in CI.
mise x -- lefthook run pre-commit \
	--tag ci --all-files --no-stage-fixed --fail-on-changes --no-auto-install --no-tty
