#!/usr/bin/env python3
"""Classify configured test subsystems before the stable Required Gate runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_CONFIGURATION_ERROR = 2
EXPECTED_KEYS = {
    "adapter",
    "integrationEnabled",
    "integrationRequired",
    "coverageEnabled",
    "coverageRequired",
    "e2eEnabled",
    "e2eRequired",
}


class InputError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--from-env", action="store_true")
    parser.add_argument("--github-output", type=Path)
    return parser.parse_args()


def load_input(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read classifier input: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputError("classifier input must be an object")
    unexpected = sorted(set(payload) - EXPECTED_KEYS)
    if unexpected:
        raise InputError("unknown classifier field(s): " + ", ".join(unexpected))
    missing = sorted(EXPECTED_KEYS - set(payload))
    if missing:
        raise InputError("missing classifier field(s): " + ", ".join(missing))
    return payload


def env_enabled(name: str) -> bool:
    return os.environ.get(name, "") == "true"


def load_environment() -> dict[str, Any]:
    coverage_enabled = env_enabled("MACOS_COVERAGE_ENABLED")
    coverage_required_value = os.environ.get("MACOS_COVERAGE_REQUIRED", "")
    return {
        "adapter": os.environ.get("MACOS_TEST_ADAPTER", ""),
        "integrationEnabled": env_enabled("MACOS_INTEGRATION_ENABLED"),
        "integrationRequired": env_enabled("MACOS_INTEGRATION_REQUIRED"),
        "coverageEnabled": coverage_enabled,
        "coverageRequired": (
            coverage_required_value == "true"
            or (coverage_enabled and coverage_required_value != "false")
        ),
        "e2eEnabled": env_enabled("MACOS_E2E_ENABLED"),
        "e2eRequired": env_enabled("MACOS_E2E_REQUIRED"),
    }


def bool_field(payload: dict[str, Any], field: str) -> bool:
    value = payload[field]
    if not isinstance(value, bool):
        raise InputError(f"{field} must be boolean")
    return value


def classify(payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    adapter = payload["adapter"]
    if not isinstance(adapter, str):
        raise InputError("adapter must be a string")

    integration_requested = bool_field(payload, "integrationEnabled")
    integration_required = bool_field(payload, "integrationRequired")
    coverage_requested = bool_field(payload, "coverageEnabled")
    coverage_required = bool_field(payload, "coverageRequired")
    e2e_requested = bool_field(payload, "e2eEnabled")
    e2e_required = bool_field(payload, "e2eRequired")

    errors: list[str] = []
    if adapter not in {"", "xcode", "swiftpm"}:
        errors.append("adapter must be xcode, swiftpm, or empty")

    configured = adapter in {"xcode", "swiftpm"}

    if integration_required and not integration_requested:
        errors.append("Integration cannot be required while disabled")
    if coverage_required and not coverage_requested:
        errors.append("Coverage cannot be required while disabled")
    if e2e_required and not e2e_requested:
        errors.append("E2E cannot be required while disabled")

    if integration_requested and not configured:
        errors.append("Integration requires a configured test adapter")
    if coverage_requested and not configured:
        errors.append("Coverage requires a configured test adapter")
    if e2e_requested and adapter != "xcode":
        errors.append("E2E requires the xcode adapter")

    result = {
        "adapter": adapter,
        "configured": configured,
        "configurationError": bool(errors),
        "errors": errors,
        "integrationEnabled": integration_requested and configured,
        "integrationRequired": integration_required,
        "coverageEnabled": coverage_requested and configured,
        "coverageRequired": coverage_required,
        "e2eEnabled": e2e_requested and adapter == "xcode",
        "e2eRequired": e2e_required,
    }
    return (EXIT_CONFIGURATION_ERROR if errors else EXIT_OK), result


def write_github_output(path: Path, result: dict[str, Any]) -> None:
    values = {
        "configured": result["configured"],
        "configuration_error": result["configurationError"],
        "integration_enabled": result["integrationEnabled"],
        "integration_required": result["integrationRequired"],
        "coverage_enabled": result["coverageEnabled"],
        "coverage_required": result["coverageRequired"],
        "e2e_enabled": result["e2eEnabled"],
        "e2e_required": result["e2eRequired"],
    }
    with path.open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={'true' if value else 'false'}\n")


def invalid_result(message: str) -> dict[str, Any]:
    return {
        "adapter": "",
        "configured": False,
        "configurationError": True,
        "errors": [message],
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": False,
        "coverageRequired": False,
        "e2eEnabled": False,
        "e2eRequired": False,
    }


def main() -> int:
    args = parse_args()
    try:
        payload = load_environment() if args.from_env else load_input(args.input)
        exit_code, result = classify(payload)
    except InputError as exc:
        exit_code = EXIT_CONFIGURATION_ERROR
        result = invalid_result(str(exc))

    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    if args.github_output is not None:
        write_github_output(args.github_output, result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
