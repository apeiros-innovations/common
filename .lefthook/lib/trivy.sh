#!/usr/bin/env bash

# Shared Trivy execution for Lefthook scripts.
# This file is intended to be sourced, not executed.

trivy_profile_scanner() {
	local profile=$1

	case "$profile" in
	terraform)
		printf '%s\n' terraform
		;;
	kubernetes)
		printf '%s\n' kubernetes
		;;
	helm)
		printf '%s\n' helm
		;;
	dockerfile)
		printf '%s\n' dockerfile
		;;
	*)
		printf \
			'trivy: unsupported scan profile: %s\n' \
			"$profile" >&2
		return 2
		;;
	esac
}

trivy_scan_directory() {
	local profile=${1:-}
	local directory=${2:-}
	local config=${3:-}
	local scanner

	[[ -n $profile ]] || {
		printf 'trivy: scan profile is required\n' >&2
		return 2
	}

	[[ -n $directory ]] || {
		printf 'trivy: scan directory is required\n' >&2
		return 2
	}

	[[ -d $directory ]] || {
		printf \
			'trivy: scan directory does not exist: %s\n' \
			"$directory" >&2
		return 2
	}

	scanner="$(trivy_profile_scanner "$profile")" ||
		return

	local -a arguments=(
		config
		--quiet
		--disable-telemetry
		--exit-code 1
		--misconfig-scanners "$scanner"
		--skip-check-update
		--skip-version-check
	)

	case "$profile" in
	terraform)
		arguments+=(
			--skip-dirs .terraform
			--skip-dirs .terragrunt-cache
		)
		;;
	esac

	if [[ -n $config ]]; then
		[[ -f $config ]] || {
			printf \
				'trivy: configuration does not exist: %s\n' \
				"$config" >&2
			return 2
		}

		arguments+=(
			--config "$config"
		)
	fi

	(
		cd -- "$directory" || exit
		trivy "${arguments[@]}" .
	)
}
