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
