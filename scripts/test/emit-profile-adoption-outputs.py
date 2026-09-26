#!/usr/bin/env python3
"""Emit strict scalar outputs for profile adoption runtime jobs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


RESOLVED_KEYS = {
    "adapter",
    "integrationEnabled",
    "integrationRequired",
    "coverageEnabled",
    "coverageRequired",
    "e2eEnabled",
    "e2eRequired",
    "visualEnabled",
    "visualRequired",
    "visualBootstrap",
}
CLASSIFIED_KEYS = RESOLVED_KEYS | {
    "configured",
    "configurationError",
    "errors",
}
OUTPUT_FIELDS = {
    "coverage_enabled": "coverageEnabled",
    "coverage_required": "coverageRequired",
    "e2e_enabled": "e2eEnabled",
    "e2e_required": "e2eRequired",
    "visual_enabled": "visualEnabled",
    "visual_required": "visualRequired",
    "visual_bootstrap": "visualBootstrap",
}


class InputError(ValueError):
    pass


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read {label}: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputError(f"{label} must be a JSON object")
    return payload


def _require_exact_keys(
    payload: dict[str, Any],
    expected: set[str],
    label: str,
) -> None:
    missing = sorted(expected - set(payload))
    unexpected = sorted(set(payload) - expected)
    if missing:
        raise InputError(f"{label} missing key(s): {', '.join(missing)}")
    if unexpected:
        raise InputError(f"{label} has unexpected key(s): {', '.join(unexpected)}")


def emit_values(
    resolved: dict[str, Any],
    classified: dict[str, Any],
) -> dict[str, str]:
    _require_exact_keys(resolved, RESOLVED_KEYS, "resolved policy")
    _require_exact_keys(classified, CLASSIFIED_KEYS, "classified policy")

    adapter = resolved["adapter"]
    if adapter not in {"swiftpm", "xcode"}:
        raise InputError("resolved adapter must be swiftpm or xcode")
    if classified["adapter"] != adapter:
        raise InputError("resolved/classified adapter mismatch")
    if classified["configured"] is not True:
        raise InputError("classified policy must be configured")
    if classified["configurationError"] is not False:
        raise InputError("classified policy reports configuration error")
    errors = classified["errors"]
    if not isinstance(errors, list) or errors:
        raise InputError("classified policy errors must be an empty array")

    values = {"adapter": adapter}
    for output_name, field in OUTPUT_FIELDS.items():
        resolved_value = resolved[field]
        classified_value = classified[field]
        if not isinstance(resolved_value, bool):
            raise InputError(f"resolved field {field} must be boolean")
        if not isinstance(classified_value, bool):
            raise InputError(f"classified field {field} must be boolean")
        if resolved_value != classified_value:
            raise InputError(f"resolved/classified policy mismatch for {field}")
        values[output_name] = "true" if resolved_value else "false"
    return values


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolved", required=True, type=Path)
    parser.add_argument("--classified", required=True, type=Path)
    parser.add_argument("--github-output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        values = emit_values(
            _load(args.resolved, "resolved policy"),
            _load(args.classified, "classified policy"),
        )
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    with args.github_output.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
