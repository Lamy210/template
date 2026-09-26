#!/usr/bin/env python3
"""Resolve named test profiles into the existing low-level test policy contract."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


EXIT_OK = 0
EXIT_CONFIGURATION_ERROR = 2
PROFILE_NAMES = {"minimal", "standard", "macos-app", "macos-ui-strict"}
XCODE_ONLY_PROFILES = {"macos-app", "macos-ui-strict"}
OVERRIDE_FIELDS = (
    "integrationEnabled",
    "integrationRequired",
    "coverageEnabled",
    "coverageRequired",
    "e2eEnabled",
    "e2eRequired",
    "visualEnabled",
    "visualRequired",
    "visualBootstrap",
)
EXPECTED_INPUT_KEYS = {"profile", "adapter", *OVERRIDE_FIELDS}
ENV_FIELDS = {
    "integrationEnabled": "MACOS_INTEGRATION_ENABLED",
    "integrationRequired": "MACOS_INTEGRATION_REQUIRED",
    "coverageEnabled": "MACOS_COVERAGE_ENABLED",
    "coverageRequired": "MACOS_COVERAGE_REQUIRED",
    "e2eEnabled": "MACOS_E2E_ENABLED",
    "e2eRequired": "MACOS_E2E_REQUIRED",
    "visualEnabled": "MACOS_VISUAL_ENABLED",
    "visualRequired": "MACOS_VISUAL_REQUIRED",
    "visualBootstrap": "MACOS_VISUAL_BOOTSTRAP",
}
PROFILES: dict[str, dict[str, bool]] = {
    "minimal": {
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": False,
        "coverageRequired": False,
        "e2eEnabled": False,
        "e2eRequired": False,
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
    },
    "standard": {
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": True,
        "coverageRequired": True,
        "e2eEnabled": False,
        "e2eRequired": False,
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
    },
    "macos-app": {
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": True,
        "coverageRequired": True,
        "e2eEnabled": True,
        "e2eRequired": True,
        "visualEnabled": False,
        "visualRequired": False,
        "visualBootstrap": False,
    },
    "macos-ui-strict": {
        "integrationEnabled": False,
        "integrationRequired": False,
        "coverageEnabled": True,
        "coverageRequired": True,
        "e2eEnabled": True,
        "e2eRequired": True,
        "visualEnabled": True,
        "visualRequired": True,
        "visualBootstrap": False,
    },
}


class InputError(ValueError):
    pass


def parse_optional_bool(value: object, field: str) -> bool | None:
    if value is None or value == "":
        return None
    if value is True or value == "true":
        return True
    if value is False or value == "false":
        return False
    raise InputError(f"{field} must be true, false, or empty")


def load_input(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read profile input: {exc}") from exc
    if not isinstance(payload, dict):
        raise InputError("profile input must be an object")

    unexpected = sorted(set(payload) - EXPECTED_INPUT_KEYS)
    if unexpected:
        raise InputError("unknown profile field(s): " + ", ".join(unexpected))
    missing = sorted(EXPECTED_INPUT_KEYS - set(payload))
    if missing:
        raise InputError("missing profile field(s): " + ", ".join(missing))
    return payload


def load_environment() -> dict[str, Any]:
    payload: dict[str, Any] = {
        "profile": os.environ.get("MACOS_TEST_PROFILE", ""),
        "adapter": os.environ.get("MACOS_TEST_ADAPTER", ""),
    }
    for field, variable in ENV_FIELDS.items():
        payload[field] = parse_optional_bool(os.environ.get(variable, ""), variable)
    return payload


def _legacy_defaults(overrides: dict[str, bool | None]) -> dict[str, bool]:
    integration_enabled = overrides["integrationEnabled"]
    integration_required = overrides["integrationRequired"]
    coverage_enabled = overrides["coverageEnabled"]
    coverage_required = overrides["coverageRequired"]
    e2e_enabled = overrides["e2eEnabled"]
    e2e_required = overrides["e2eRequired"]
    visual_enabled = overrides["visualEnabled"]
    visual_required = overrides["visualRequired"]
    visual_bootstrap = overrides["visualBootstrap"]

    resolved_coverage_enabled = coverage_enabled is True
    resolved_visual_enabled = visual_enabled is True
    return {
        "integrationEnabled": integration_enabled is True,
        "integrationRequired": integration_required is True,
        "coverageEnabled": resolved_coverage_enabled,
        "coverageRequired": (
            resolved_coverage_enabled
            if coverage_required is None
            else coverage_required
        ),
        "e2eEnabled": e2e_enabled is True,
        "e2eRequired": e2e_required is True,
        "visualEnabled": resolved_visual_enabled,
        "visualRequired": (
            resolved_visual_enabled
            if visual_required is None
            else visual_required
        ),
        "visualBootstrap": visual_bootstrap is True,
    }


def resolve(payload: dict[str, Any]) -> dict[str, object]:
    profile = payload.get("profile")
    adapter = payload.get("adapter")
    if not isinstance(profile, str):
        raise InputError("profile must be a string")
    if not isinstance(adapter, str):
        raise InputError("adapter must be a string")
    if profile and profile not in PROFILE_NAMES:
        raise InputError(f"unsupported test profile: {profile}")
    if profile and adapter not in {"swiftpm", "xcode"}:
        raise InputError("named test profiles require adapter xcode or swiftpm")
    if profile in XCODE_ONLY_PROFILES and adapter != "xcode":
        raise InputError(f"test profile {profile} requires the xcode adapter")

    overrides = {
        field: parse_optional_bool(payload.get(field), field)
        for field in OVERRIDE_FIELDS
    }

    if profile:
        policy = dict(PROFILES[profile])
        for field, value in overrides.items():
            if value is not None:
                policy[field] = value
    else:
        policy = _legacy_defaults(overrides)

    return {"adapter": adapter, **policy}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-env", action="store_true")
    source.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def write_output(path: Path, policy: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(policy, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    try:
        payload = load_environment() if args.from_env else load_input(args.input)
        policy = resolve(payload)
        write_output(args.output, policy)
    except InputError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_CONFIGURATION_ERROR

    profile = payload["profile"] or "legacy"
    adapter = policy["adapter"] or "unconfigured"
    print(f"Resolved test profile {profile!r} for adapter {adapter!r}.")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
