#!/usr/bin/env bash
set -euo pipefail

[ "$#" -eq 0 ] && exit 0

for f in "$@"; do
  [ -f "$f" ] || continue
  perl -0777 -i -pe 's/\n*\z/\n/' "$f"
done
