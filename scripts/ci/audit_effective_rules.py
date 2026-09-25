from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


CANONICAL_CHECKS = {
    "Required gate",
    "Tests / Required Gate",
    "swift-quality / Swift quality",
}
EXPECTED_RULE_TYPES = {
    "deletion",
    "non_fast_forward",
    "required_linear_history",
    "pull_request",
    "required_status_checks",
}


def _rule_id(rule: dict[str, Any]) -> str:
    value = rule.get("ruleset_id")
    if type(value) is int and value > 0:
        return str(value)
    return "unknown"


def _group_rules(rules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for rule in rules:
        rule_type = rule.get("type")
        if isinstance(rule_type, str):
            grouped.setdefault(rule_type, []).append(rule)
    return grouped


def _require_single_rule(
    grouped: dict[str, list[dict[str, Any]]],
    rule_type: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    rules = grouped.get(rule_type, [])
    if not rules:
        errors.append(f"{rule_type} rule is required")
    elif len(rules) != 1:
        ids = ", ".join(_rule_id(rule) for rule in rules)
        errors.append(
            f"{rule_type} rule must appear exactly once; active ruleset IDs: [{ids}]"
        )
    return rules


def _validate_pull_request_rule(rule: dict[str, Any]) -> list[str]:
    prefix = f"pull_request ruleset {_rule_id(rule)}"
    parameters = rule.get("parameters")
    if not isinstance(parameters, dict):
        return [f"{prefix}: parameters must be an object"]

    errors: list[str] = []
    approval_count = parameters.get("required_approving_review_count")
    if type(approval_count) is not int or approval_count != 0:
        errors.append(f"{prefix}: required_approving_review_count must equal 0")

    if parameters.get("dismiss_stale_reviews_on_push") is not True:
        errors.append(f"{prefix}: dismiss_stale_reviews_on_push must be true")
    if parameters.get("required_review_thread_resolution") is not True:
        errors.append(f"{prefix}: required_review_thread_resolution must be true")
    if parameters.get("require_code_owner_review") is not False:
        errors.append(f"{prefix}: require_code_owner_review must be false")
    if parameters.get("require_last_push_approval") is not False:
        errors.append(f"{prefix}: require_last_push_approval must be false")

    reviewers = parameters.get("required_reviewers", [])
    if reviewers != []:
        errors.append(f"{prefix}: required_reviewers must be empty")

    if parameters.get("require_extra_approval_for_unattributed_changes", False) is not False:
        errors.append(
            f"{prefix}: require_extra_approval_for_unattributed_changes must be false"
        )

    if parameters.get("allowed_merge_methods") != ["squash"]:
        errors.append(f"{prefix}: allowed_merge_methods must equal ['squash']")

    return errors


def _validate_status_rule(rule: dict[str, Any]) -> list[str]:
    prefix = f"required_status_checks ruleset {_rule_id(rule)}"
    parameters = rule.get("parameters")
    if not isinstance(parameters, dict):
        return [f"{prefix}: parameters must be an object"]

    errors: list[str] = []
    if parameters.get("strict_required_status_checks_policy") is not True:
        errors.append(
            f"{prefix}: strict_required_status_checks_policy must be true"
        )
    if parameters.get("do_not_enforce_on_create", False) is not False:
        errors.append(f"{prefix}: do_not_enforce_on_create must be false")

    checks = parameters.get("required_status_checks")
    if not isinstance(checks, list):
        errors.append(
            f"{prefix}: required check contexts must equal {sorted(CANONICAL_CHECKS)!r}"
        )
        return errors

    contexts: list[str] = []
    for item in checks:
        if not isinstance(item, dict):
            errors.append(f"{prefix}: required check entries must be objects")
            continue
        context = item.get("context")
        if not isinstance(context, str) or not context:
            errors.append(f"{prefix}: required check contexts must be non-empty strings")
            continue
        contexts.append(context)

    if (
        len(contexts) != len(set(contexts))
        or set(contexts) != CANONICAL_CHECKS
    ):
        errors.append(
            f"{prefix}: required check contexts must equal {sorted(CANONICAL_CHECKS)!r}"
        )

    return errors


def validate_effective_main_rules(document: object) -> list[str]:
    if not isinstance(document, list):
        return ["effective main rules must be a JSON array"]
    if any(
        not isinstance(rule, dict) or not isinstance(rule.get("type"), str)
        for rule in document
    ):
        return ["effective main rule entries must be objects with a string type"]

    rules = [rule for rule in document if isinstance(rule, dict)]
    grouped = _group_rules(rules)
    errors: list[str] = []

    unexpected = sorted(set(grouped) - EXPECTED_RULE_TYPES)
    if unexpected:
        errors.append(f"unexpected effective main rule types: {unexpected!r}")

    for rule_type in sorted(EXPECTED_RULE_TYPES):
        active = _require_single_rule(grouped, rule_type, errors)
        if rule_type == "pull_request":
            for rule in active:
                errors.extend(_validate_pull_request_rule(rule))
        elif rule_type == "required_status_checks":
            for rule in active:
                errors.extend(_validate_status_rule(rule))

    return errors


def _flatten_payload(payload: object) -> object:
    if (
        isinstance(payload, list)
        and payload
        and all(isinstance(page, list) for page in payload)
    ):
        return [rule for page in payload for rule in page]
    return payload


def _load_payload(path: str) -> object:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit GitHub's effective active rules for the default branch."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default="-",
        help="JSON from GET /repos/{owner}/{repo}/rules/branches/{branch}; default: stdin",
    )
    args = parser.parse_args(argv)

    try:
        payload = _flatten_payload(_load_payload(args.path))
    except (OSError, json.JSONDecodeError) as error:
        print(f"unable to read effective rules JSON: {error}", file=sys.stderr)
        return 2

    errors = validate_effective_main_rules(payload)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1

    print("effective default-branch rules match the Solo governance contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
