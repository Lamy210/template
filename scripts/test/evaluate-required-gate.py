#!/usr/bin/env python3
"""Evaluate stable required-test gate policy from normalized subsystem results."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

EXPECTED_SUBSYSTEMS = ("Unit", "Integration", "E2E", "Visual", "Coverage")
VALID_STATUSES = {"success", "failure", "not-applicable", "disabled"}
VALID_CLASSIFICATIONS = {"applicable", "not-applicable"}

EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_CONFIGURATION_ERROR = 2


class InputError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    return parser.parse_args()


def load_payload(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"cannot read input: {exc}") from exc


def base_output() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "passed",
        "blocking": [],
        "warnings": [],
        "configurationErrors": [],
        "subsystems": {},
    }


def evaluate(payload: Any) -> tuple[int, dict[str, Any]]:
    output = base_output()
    if not isinstance(payload, dict):
        output["status"] = "configuration-error"
        output["configurationErrors"].append("input must be an object")
        return EXIT_CONFIGURATION_ERROR, output
    if payload.get("schemaVersion") != 1:
        output["status"] = "configuration-error"
        output["configurationErrors"].append("schemaVersion must equal 1")
        return EXIT_CONFIGURATION_ERROR, output

    raw_subsystems = payload.get("subsystems")
    if not isinstance(raw_subsystems, dict):
        output["status"] = "configuration-error"
        output["configurationErrors"].append("subsystems must be an object")
        return EXIT_CONFIGURATION_ERROR, output

    unexpected = sorted(set(raw_subsystems) - set(EXPECTED_SUBSYSTEMS))
    if unexpected:
        output["status"] = "configuration-error"
        output["configurationErrors"].append(
            "unknown subsystem(s): " + ", ".join(unexpected)
        )

    configured_count = 0

    for name in EXPECTED_SUBSYSTEMS:
        raw = raw_subsystems.get(name)
        if raw is None:
            output["blocking"].append(f"{name}: missing result")
            output["subsystems"][name] = {"status": "missing"}
            continue
        if not isinstance(raw, dict):
            output["configurationErrors"].append(f"{name}: result must be an object")
            output["subsystems"][name] = {"status": "invalid"}
            continue

        status = raw.get("status")
        required = raw.get("required")
        classification = raw.get("classification")
        normalized = {
            "status": status,
            "required": required,
            "classification": classification,
        }
        output["subsystems"][name] = normalized

        if not isinstance(required, bool):
            output["configurationErrors"].append(f"{name}: required must be boolean")
            continue
        if classification not in VALID_CLASSIFICATIONS:
            output["configurationErrors"].append(
                f"{name}: classification must be applicable or not-applicable"
            )
            continue
        if status not in VALID_STATUSES:
            output["blocking"].append(f"{name}: unexpected status {status!r}")
            continue

        if status != "disabled":
            configured_count += 1

        if status == "disabled":
            if required:
                output["configurationErrors"].append(
                    f"{name}: disabled subsystem cannot be required"
                )
            elif classification != "not-applicable":
                output["configurationErrors"].append(
                    f"{name}: disabled subsystem must be classified not-applicable"
                )
            continue

        if status == "not-applicable":
            if classification != "not-applicable":
                output["configurationErrors"].append(
                    f"{name}: not-applicable status requires explicit not-applicable classification"
                )
            continue

        if classification != "applicable":
            output["configurationErrors"].append(
                f"{name}: {status} status requires applicable classification"
            )
            continue

        if status == "failure":
            if required:
                output["blocking"].append(f"{name}: required subsystem failed")
            else:
                output["warnings"].append(f"{name}: optional subsystem failed")

    if output["configurationErrors"]:
        output["status"] = "configuration-error"
        return EXIT_CONFIGURATION_ERROR, output
    if output["blocking"]:
        output["status"] = "failed"
        return EXIT_FAILED, output
    if configured_count == 0:
        output["status"] = "not-configured"
    return EXIT_PASSED, output


def main() -> int:
    args = parse_args()
    try:
        payload = load_payload(args.input)
        exit_code, output = evaluate(payload)
    except InputError as exc:
        exit_code = EXIT_CONFIGURATION_ERROR
        output = base_output()
        output["status"] = "configuration-error"
        output["configurationErrors"].append(str(exc))

    json.dump(output, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
