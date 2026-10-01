from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    workflow_job_ranges,
    yaml_key_pattern,
)


ENVIRONMENT_RE = re.compile(
    rf"^(?P<indent>\s*){yaml_key_pattern('environment')}:\s*(?P<value>.*?)\s*$"
)
PULL_REQUEST_TARGET_RE = re.compile(
    rf"^  {yaml_key_pattern('pull_request_target')}:\s*(?:#.*)?$"
)
ON_INLINE_RE = re.compile(
    rf"^{yaml_key_pattern('on')}:\s*(?P<value>.+?)\s*$"
)
SECRETS_INHERIT_RE = re.compile(
    rf"^\s*{yaml_key_pattern('secrets')}:\s*(?:inherit|\"inherit\"|'inherit')\s*(?:#.*)?$"
)

ALLOWED_ENVIRONMENTS: dict[tuple[str, str], str] = {
    (
        ".github/workflows/reusable-macos-release.yml",
        "release",
    ): "release",
    (
        "examples/release-environment-proof.yml",
        "environment-probe",
    ): "release",
}


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    scope: str
    message: str


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, character in enumerate(value):
        if character == "'" and not in_double:
            in_single = not in_single
        elif character == '"' and not in_single:
            in_double = not in_double
        elif character == "#" and not in_single and not in_double:
            if index == 0 or value[index - 1].isspace():
                return value[:index].rstrip()
    return value.rstrip()


def _unquote(value: str) -> str:
    value = _strip_inline_comment(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _job_for_line(lines: list[str], line_index: int) -> str | None:
    for job, start, end in workflow_job_ranges(lines):
        if start < line_index < end:
            return job
    return None


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    lines = text.splitlines()
    violations: list[PolicyViolation] = []
    relative = path.as_posix()

    for index, raw in enumerate(lines):
        inline_trigger = ON_INLINE_RE.match(raw)
        has_pull_request_target = PULL_REQUEST_TARGET_RE.match(raw) is not None
        if inline_trigger is not None:
            trigger_value = _strip_inline_comment(
                inline_trigger.group("value")
            )
            has_pull_request_target = (
                re.search(r"\bpull_request_target\b", trigger_value) is not None
            )

        if has_pull_request_target:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope="workflow",
                    message="pull_request_target is forbidden",
                )
            )

        if SECRETS_INHERIT_RE.match(raw):
            job = _job_for_line(lines, index)
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope=f"job:{job}" if job is not None else "workflow",
                    message="secrets: inherit is forbidden; map narrow named secrets",
                )
            )

        environment = ENVIRONMENT_RE.match(raw)
        if environment is None:
            continue

        job = _job_for_line(lines, index)
        scope = f"job:{job}" if job is not None else "workflow"
        value = _unquote(environment.group("value"))
        expected = (
            ALLOWED_ENVIRONMENTS.get((relative, job))
            if job is not None
            else None
        )
        if expected is None:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope=scope,
                    message=(
                        "GitHub Environment usage is forbidden outside the "
                        "explicit release-boundary allowlist"
                    ),
                )
            )
        elif value != expected:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope=scope,
                    message=(
                        f"allowlisted Environment must be literal {expected!r}; "
                        f"found {value!r}"
                    ),
                )
            )

    for (allowed_path, allowed_job), expected in ALLOWED_ENVIRONMENTS.items():
        if relative != allowed_path:
            continue
        found = False
        for index, raw in enumerate(lines):
            environment = ENVIRONMENT_RE.match(raw)
            if environment is None:
                continue
            if _job_for_line(lines, index) != allowed_job:
                continue
            found = _unquote(environment.group("value")) == expected
            if found:
                break
        if not found:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=1,
                    scope=f"job:{allowed_job}",
                    message=(
                        "required release-boundary Environment is missing or no "
                        f"longer equals {expected!r}"
                    ),
                )
            )

    return violations


def validate_repository(root: Path) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for path in workflow_paths(root):
        violations.extend(
            validate_workflow_text(
                path.relative_to(root),
                path.read_text(encoding="utf-8"),
            )
        )
    return violations
