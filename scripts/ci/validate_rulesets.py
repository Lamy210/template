from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

RUNTIME_ONLY_FIELDS = {
    "id",
    "node_id",
    "source",
    "_links",
    "created_at",
    "updated_at",
}
CANONICAL_CHECKS = {
    "Required gate",
    "swift-quality / Swift quality",
}
SINGLETON_MAIN_RULES = {
    "deletion",
    "non_fast_forward",
    "required_linear_history",
    "pull_request",
    "required_status_checks",
}
REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_PROFILES = (
    (REPO_ROOT / "rulesets/main-solo.json", "main-solo"),
    (REPO_ROOT / "rulesets/release-tags.json", "release-tags"),
)


class RulesetValidationError(ValueError):
    pass


def _runtime_metadata_errors(document: dict) -> list[str]:
    return [
        f"runtime-only field '{field}' is forbidden"
        for field in sorted(RUNTIME_ONLY_FIELDS.intersection(document))
    ]


def _rules_by_type(document: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    rules = document.get("rules")
    if not isinstance(rules, list):
        return grouped

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_type = rule.get("type")
        if isinstance(rule_type, str):
            grouped.setdefault(rule_type, []).append(rule)
    return grouped


def _ref_name(document: dict) -> dict | None:
    conditions = document.get("conditions")
    if not isinstance(conditions, dict):
        return None
    ref_name = conditions.get("ref_name")
    return ref_name if isinstance(ref_name, dict) else None


def _validate_common(
    document: dict,
    *,
    target: str,
    expected_include: list[str],
) -> list[str]:
    errors = _runtime_metadata_errors(document)

    if document.get("target") != target:
        errors.append(f"target must equal '{target}'")
    if document.get("enforcement") != "active":
        errors.append("enforcement must equal 'active'")
    if document.get("bypass_actors") != []:
        errors.append("bypass_actors must be empty")

    ref_name = _ref_name(document)
    if ref_name is None:
        errors.append("conditions.ref_name must be an object")
    else:
        if ref_name.get("include") != expected_include:
            errors.append(f"ref_name.include must equal {expected_include!r}")
        if ref_name.get("exclude") != []:
            errors.append("ref_name.exclude must be empty")

    if not isinstance(document.get("rules"), list):
        errors.append("rules must be an array")

    return errors


def _single_rule(
    grouped: dict[str, list[dict]],
    rule_type: str,
    errors: list[str],
) -> dict | None:
    rules = grouped.get(rule_type, [])
    if len(rules) != 1:
        errors.append(f"{rule_type} rule must appear exactly once")
        return None
    return rules[0]


def validate_main_solo(document: dict) -> list[str]:
    if not isinstance(document, dict):
        return ["ruleset document must be a JSON object"]

    errors = _validate_common(
        document,
        target="branch",
        expected_include=["~DEFAULT_BRANCH"],
    )
    grouped = _rules_by_type(document)

    for rule_type in sorted(SINGLETON_MAIN_RULES):
        _single_rule(grouped, rule_type, errors)

    pull_request_rules = grouped.get("pull_request", [])
    if len(pull_request_rules) == 1:
        parameters = pull_request_rules[0].get("parameters")
        if not isinstance(parameters, dict):
            errors.append("pull_request.parameters must be an object")
        else:
            if parameters.get("required_approving_review_count") != 0:
                errors.append("required_approving_review_count must equal 0")
            if parameters.get("required_review_thread_resolution") is not True:
                errors.append("required_review_thread_resolution must be true")
            if parameters.get("require_code_owner_review") is not False:
                errors.append("require_code_owner_review must be false")
            if parameters.get("require_last_push_approval") is not False:
                errors.append("require_last_push_approval must be false")
            if parameters.get("allowed_merge_methods") != ["squash"]:
                errors.append("allowed_merge_methods must equal ['squash']")

    status_rules = grouped.get("required_status_checks", [])
    if len(status_rules) == 1:
        parameters = status_rules[0].get("parameters")
        if not isinstance(parameters, dict):
            errors.append("required_status_checks.parameters must be an object")
        else:
            if parameters.get("strict_required_status_checks_policy") is not True:
                errors.append("strict_required_status_checks_policy must be true")
            checks = parameters.get("required_status_checks")
            contexts: list[str | None] = []
            if isinstance(checks, list):
                contexts = [
                    item.get("context") if isinstance(item, dict) else None
                    for item in checks
                ]
            if (
                not isinstance(checks, list)
                or len(contexts) != len(set(contexts))
                or set(contexts) != CANONICAL_CHECKS
            ):
                errors.append(
                    "required check contexts must equal "
                    "{'Required gate', 'swift-quality / Swift quality'}"
                )

    return errors


def validate_release_tags(document: dict) -> list[str]:
    if not isinstance(document, dict):
        return ["ruleset document must be a JSON object"]

    errors = _validate_common(
        document,
        target="tag",
        expected_include=["refs/tags/v*"],
    )
    grouped = _rules_by_type(document)

    update_rules = grouped.get("update", [])
    if len(update_rules) != 1:
        errors.append("release tag update restriction is required")
    else:
        parameters = update_rules[0].get("parameters")
        if parameters != {"update_allows_fetch_and_merge": False}:
            errors.append(
                "release tag update parameters must equal "
                "{'update_allows_fetch_and_merge': false}"
            )

    deletion_rules = grouped.get("deletion", [])
    if len(deletion_rules) != 1:
        errors.append("release tag deletion restriction is required")

    for forbidden_type in ("pull_request", "required_status_checks"):
        if forbidden_type in grouped:
            errors.append(f"{forbidden_type} is not allowed for release tags")

    return errors


def validate_file(path: Path, profile: str) -> list[str]:
    if not path.is_file():
        return [f"{path}: file not found"]

    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except json.JSONDecodeError as error:
        return [f"{path}: invalid JSON: {error.msg} at line {error.lineno} column {error.colno}"]

    validators: dict[str, Callable[[dict], list[str]]] = {
        "main-solo": validate_main_solo,
        "release-tags": validate_release_tags,
    }
    validator = validators.get(profile)
    if validator is None:
        return [f"{path}: unknown profile '{profile}'"]

    return [f"{path}: {error}" for error in validator(document)]


def main(argv: list[str] | None = None) -> int:
    if argv not in (None, []):
        print("validate_rulesets.py does not accept positional arguments", file=sys.stderr)
        return 2

    errors: list[str] = []
    for path, profile in CANONICAL_PROFILES:
        errors.extend(validate_file(path, profile))

    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
