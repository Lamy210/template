from __future__ import annotations

from typing import Any


ENVIRONMENT_NAME = "release"


def _flatten_policy_pages(payload: object) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(payload, dict):
        pages = [payload]
    elif isinstance(payload, list) and all(isinstance(page, dict) for page in payload):
        pages = payload
    else:
        return [], ["deployment branch policies must be an object or an array of page objects"]

    policies: list[dict[str, Any]] = []
    errors: list[str] = []
    declared_total: int | None = None

    for page_index, page in enumerate(pages):
        total_count = page.get("total_count")
        if type(total_count) is not int or total_count < 0:
            errors.append(
                f"deployment policy page {page_index}: total_count must be a non-negative integer"
            )
        elif declared_total is None:
            declared_total = total_count
        elif total_count != declared_total:
            errors.append("deployment policy pages disagree on total_count")

        branch_policies = page.get("branch_policies")
        if not isinstance(branch_policies, list):
            errors.append(
                f"deployment policy page {page_index}: branch_policies must be an array"
            )
            continue
        for policy in branch_policies:
            if not isinstance(policy, dict):
                errors.append("deployment policy entries must be objects")
                continue
            policies.append(policy)

    if declared_total is not None and declared_total != len(policies):
        errors.append(
            f"deployment policy total_count={declared_total} does not match fetched entries={len(policies)}"
        )

    return policies, errors


def validate_release_environment(
    environment: object,
    policies_payload: object,
    default_branch: str,
) -> list[str]:
    errors: list[str] = []

    if not isinstance(default_branch, str) or not default_branch:
        errors.append("default branch must be a non-empty string")

    if not isinstance(environment, dict):
        return ["release Environment response must be a JSON object"] + errors

    if environment.get("name") != ENVIRONMENT_NAME:
        errors.append("Environment name must equal 'release'")

    deployment_policy = environment.get("deployment_branch_policy")
    valid_custom_policy = (
        isinstance(deployment_policy, dict)
        and deployment_policy.get("protected_branches") is False
        and deployment_policy.get("custom_branch_policies") is True
    )
    if not valid_custom_policy:
        errors.append(
            "release Environment must use custom deployment branch policies "
            "(protected_branches=false, custom_branch_policies=true)"
        )

    policies, policy_errors = _flatten_policy_pages(policies_payload)
    errors.extend(policy_errors)

    if len(policies) != 1:
        errors.append(
            f"release Environment must have exactly one deployment policy; found {len(policies)}"
        )
        return errors

    policy = policies[0]
    policy_id = policy.get("id")
    if type(policy_id) is not int or policy_id <= 0:
        errors.append("deployment policy id must be a positive integer")

    policy_name = policy.get("name")
    if policy_name != default_branch:
        errors.append(
            f"deployment policy name must equal default branch {default_branch!r}"
        )

    policy_type = policy.get("type")
    if policy_type is not None and policy_type != "branch":
        errors.append("deployment policy type must be branch when GitHub returns type")

    return errors
