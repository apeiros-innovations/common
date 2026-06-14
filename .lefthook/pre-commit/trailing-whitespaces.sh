#!/usr/bin/env bash
set -euo pipefail

[ "$#" -eq 0 ] && exit 0

for f in "$@"; do
  [ -f "$f" ] || continue
  sed -i.bak -e 's/[[:space:]]\+$//' "$f" && rm -f "$f.bak"
done
