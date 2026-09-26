#!/usr/bin/env python3
"""Compare normalized coverage summaries using a profile-aware ratchet."""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

FINGERPRINT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONSISTENCY_TOLERANCE = Decimal("0.000001")
EXIT_PASSED = 0
EXIT_REGRESSION = 1
EXIT_INVALID = 2
EXIT_MIGRATION_REQUIRED = 3


class ValidationError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--current", required=True, type=Path)
    parser.add_argument("--max-regression", default="0.001")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle, parse_float=Decimal)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc


def decimal_value(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be numeric")
    try:
        result = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"{field} must be numeric") from exc
    if not result.is_finite():
        raise ValidationError(f"{field} must be finite")
    return result


def integer_value(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{field} must be an integer")
    if value < 0:
        raise ValidationError(f"{field} must be >= 0")
    return value


def validate_counts(block: Any, field: str) -> dict[str, Any]:
    if not isinstance(block, dict):
        raise ValidationError(f"{field} must be an object")
    covered = integer_value(block.get("coveredLines"), f"{field}.coveredLines")
    executable = integer_value(block.get("executableLines"), f"{field}.executableLines")
    if covered > executable:
        raise ValidationError(
            f"{field}.coveredLines ({covered}) exceeds executableLines ({executable})"
        )
    ratio = decimal_value(block.get("lineCoverage"), f"{field}.lineCoverage")
    if ratio < 0 or ratio > 1:
        raise ValidationError(f"{field}.lineCoverage must be within 0...1")
    expected = Decimal(0) if executable == 0 else Decimal(covered) / Decimal(executable)
    if abs(ratio - expected) > CONSISTENCY_TOLERANCE:
        raise ValidationError(
            f"{field}.lineCoverage is inconsistent with coveredLines/executableLines"
        )
    return {
        "coveredLines": covered,
        "executableLines": executable,
        "lineCoverage": ratio,
    }


def validate_summary(payload: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValidationError(f"{label} must be an object")
    if payload.get("schemaVersion") != 1:
        raise ValidationError(f"{label}.schemaVersion must equal 1")
    fingerprint = payload.get("coverageProfileFingerprint")
    if not isinstance(fingerprint, str) or not FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValidationError(
            f"{label}.coverageProfileFingerprint must be sha256:<64 lowercase hex>"
        )
    totals = validate_counts(payload.get("totals"), f"{label}.totals")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, dict):
        raise ValidationError(f"{label}.targets must be an object")
    targets: dict[str, dict[str, Any]] = {}
    for name, block in raw_targets.items():
        if not isinstance(name, str) or not name:
            raise ValidationError(f"{label}.targets keys must be non-empty strings")
        targets[name] = validate_counts(block, f"{label}.targets[{name!r}]")
    return {
        "coverageProfileFingerprint": fingerprint,
        "totals": totals,
        "targets": targets,
    }


def json_number(value: Decimal) -> float:
    return float(value)


def block_report(
    baseline: dict[str, Any], current: dict[str, Any], max_regression: Decimal
) -> dict[str, Any]:
    regression = baseline["lineCoverage"] - current["lineCoverage"]
    return {
        "baseline": {
            "coveredLines": baseline["coveredLines"],
            "executableLines": baseline["executableLines"],
            "lineCoverage": json_number(baseline["lineCoverage"]),
        },
        "current": {
            "coveredLines": current["coveredLines"],
            "executableLines": current["executableLines"],
            "lineCoverage": json_number(current["lineCoverage"]),
        },
        "coverageDelta": json_number(current["lineCoverage"] - baseline["lineCoverage"]),
        "regressionAmount": json_number(max(regression, Decimal(0))),
        "rawCountsChanged": (
            baseline["coveredLines"] != current["coveredLines"]
            or baseline["executableLines"] != current["executableLines"]
        ),
        "denominatorChanged": baseline["executableLines"] != current["executableLines"],
        "regressed": regression > max_regression,
    }


def compare(
    baseline: dict[str, Any], current: dict[str, Any], max_regression: Decimal
) -> tuple[int, dict[str, Any]]:
    if baseline["coverageProfileFingerprint"] != current["coverageProfileFingerprint"]:
        return EXIT_MIGRATION_REQUIRED, {
            "status": "migration-required",
            "baselineProfileFingerprint": baseline["coverageProfileFingerprint"],
            "currentProfileFingerprint": current["coverageProfileFingerprint"],
            "maxRegression": json_number(max_regression),
        }

    overall = block_report(baseline["totals"], current["totals"], max_regression)
    target_reports: dict[str, Any] = {}
    target_regression = False
    for name in sorted(set(baseline["targets"]) & set(current["targets"])):
        report = block_report(baseline["targets"][name], current["targets"][name], max_regression)
        target_reports[name] = report
        target_regression = target_regression or report["regressed"]

    payload = {
        "status": "regression" if overall["regressed"] or target_regression else "passed",
        "maxRegression": json_number(max_regression),
        "profileFingerprint": baseline["coverageProfileFingerprint"],
        "overall": overall,
        "targets": target_reports,
        "targetSetChanged": set(baseline["targets"]) != set(current["targets"]),
        "baselineOnlyTargets": sorted(set(baseline["targets"]) - set(current["targets"])),
        "currentOnlyTargets": sorted(set(current["targets"]) - set(baseline["targets"])),
    }
    return (
        EXIT_REGRESSION if payload["status"] == "regression" else EXIT_PASSED,
        payload,
    )


def main() -> int:
    args = parse_args()
    try:
        max_regression = decimal_value(args.max_regression, "maxRegression")
        if max_regression < 0 or max_regression > 1:
            raise ValidationError("maxRegression must be within 0...1")
        baseline = validate_summary(load_json(args.baseline), "baseline")
        current = validate_summary(load_json(args.current), "current")
        exit_code, payload = compare(baseline, current, max_regression)
    except ValidationError as exc:
        exit_code = EXIT_INVALID
        payload = {"status": "invalid", "error": str(exc)}

    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
