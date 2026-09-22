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
    "visualEnabled",
    "visualRequired",
    "visualBootstrap",
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


def optional_env_bool(name: str) -> bool | None:
    value = os.environ.get(name, "")
    if value == "":
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    raise InputError(f"{name} must be true, false, or empty")


def load_environment() -> dict[str, Any]:
    integration_enabled = optional_env_bool("MACOS_INTEGRATION_ENABLED") is True
    integration_required = optional_env_bool("MACOS_INTEGRATION_REQUIRED") is True
    coverage_enabled = optional_env_bool("MACOS_COVERAGE_ENABLED") is True
    coverage_required_value = optional_env_bool("MACOS_COVERAGE_REQUIRED")
    e2e_enabled = optional_env_bool("MACOS_E2E_ENABLED") is True
    e2e_required = optional_env_bool("MACOS_E2E_REQUIRED") is True
    visual_enabled = optional_env_bool("MACOS_VISUAL_ENABLED") is True
    visual_required_value = optional_env_bool("MACOS_VISUAL_REQUIRED")
    visual_bootstrap = optional_env_bool("MACOS_VISUAL_BOOTSTRAP") is True

    return {
        "adapter": os.environ.get("MACOS_TEST_ADAPTER", ""),
        "integrationEnabled": integration_enabled,
        "integrationRequired": integration_required,
        "coverageEnabled": coverage_enabled,
        "coverageRequired": (
            coverage_enabled
            if coverage_required_value is None
            else coverage_required_value
        ),
        "e2eEnabled": e2e_enabled,
        "e2eRequired": e2e_required,
        "visualEnabled": visual_enabled,
        "visualRequired": (
            visual_enabled
            if visual_required_value is None
            else visual_required_value
        ),
        "visualBootstrap": visual_bootstrap,
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
    visual_requested = bool_field(payload, "visualEnabled")
    visual_required = bool_field(payload, "visualRequired")
    visual_bootstrap = bool_field(payload, "visualBootstrap")

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
    if visual_required and not visual_requested:
        errors.append("Visual cannot be required while disabled")
    if visual_bootstrap and not visual_requested:
        errors.append("Visual bootstrap requires Visual to be enabled")

    if integration_requested and not configured:
        errors.append("Integration requires a configured test adapter")
    if coverage_requested and not configured:
        errors.append("Coverage requires a configured test adapter")
    if e2e_requested and adapter != "xcode":
        errors.append("E2E requires the xcode adapter")
    if visual_requested and adapter != "xcode":
        errors.append("Visual requires the xcode adapter")
    if visual_requested and not e2e_requested:
        errors.append("Visual requires E2E to be enabled")

    visual_enabled = visual_requested and adapter == "xcode" and e2e_requested
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
        "visualEnabled": visual_enabled,
        "visualRequired": visual_required,
        "visualBootstrap": visual_bootstrap,
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
        "visual_enabled": result["visualEnabled"],
        "visual_required": result["visualRequired"],
        "visual_bootstrap": result["visualBootstrap"],
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
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
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
