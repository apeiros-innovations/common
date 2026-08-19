#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path


def reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key!r}")
        result[key] = value

    return result


def reject_nonstandard_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


failed = False

for filename in sys.argv[1:]:
    path = Path(filename)

    if not path.is_file():
        continue

    try:
        with path.open("r", encoding="utf-8") as file:
            json.load(
                file,
                object_pairs_hook=reject_duplicate_keys,
                parse_constant=reject_nonstandard_constant,
            )
    except json.JSONDecodeError as error:
        print(
            f"{path}:{error.lineno}:{error.colno}: {error.msg}",
            file=sys.stderr,
        )
        failed = True
    except UnicodeDecodeError as error:
        print(f"{path}: invalid UTF-8: {error}", file=sys.stderr)
        failed = True
    except ValueError as error:
        print(f"{path}: {error}", file=sys.stderr)
        failed = True

raise SystemExit(1 if failed else 0)
