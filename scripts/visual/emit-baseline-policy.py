#!/usr/bin/env python3
"""Emit whether a validated visual manifest needs a rolling-main baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


class InputError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in pairs:
        if key in payload:
            raise InputError(f"duplicate JSON key: {key}")
        payload[key] = value
    return payload


def requires_rolling_baseline(document: object) -> bool:
    if not isinstance(document, dict):
        raise InputError("visual manifest must be a JSON object")

    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise InputError("visual manifest cases must be a non-empty array")

    requires_rolling = False
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise InputError(f"visual manifest case {index} must be an object")
        baseline = case.get("baseline")
        if baseline not in {"git", "rolling-main"}:
            raise InputError(
                f"visual manifest case {index} has unsupported baseline: {baseline!r}"
            )
        if baseline == "rolling-main":
            requires_rolling = True

    return requires_rolling


def load_manifest(path: Path) -> object:
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
        )
    except OSError as exc:
        raise InputError(f"cannot read visual manifest: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise InputError(f"invalid visual manifest JSON: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    args = parser.parse_args()

    try:
        requires_rolling = requires_rolling_baseline(load_manifest(args.manifest))
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with args.github_output.open("a", encoding="utf-8") as handle:
        handle.write(
            f"requires_rolling={'true' if requires_rolling else 'false'}\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
