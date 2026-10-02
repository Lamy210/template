from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    YAML_KEY_TOKEN,
    YAML_MAPPING_KEY_RE,
    normalize_yaml_key,
    strip_yaml_inline_comment,
    workflow_job_ranges,
    yaml_key_pattern,
    yaml_line_indent,
    yaml_mapping_child_indent,
)


ENVIRONMENT_RE = re.compile(
    rf"^(?P<indent>\s*){yaml_key_pattern('environment')}:\s*(?P<value>.*?)\s*$"
)
ON_RE = re.compile(
    rf"^{yaml_key_pattern('on')}:\s*(?P<value>.*?)\s*$"
)
SECRETS_RE = re.compile(
    rf"^(?P<indent>\s*){yaml_key_pattern('secrets')}:\s*(?P<value>.*?)\s*$"
)
INLINE_TRIGGER_TOKEN_RE = re.compile(rf"^(?:{YAML_KEY_TOKEN})$")


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


def _unquote(value: str) -> str:
    value = strip_yaml_inline_comment(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _inline_trigger_tokens(value: str) -> list[str] | None:
    value = strip_yaml_inline_comment(value).strip()
    if not value:
        return []

    if value.startswith("["):
        if not value.endswith("]"):
            return None
        inner = value[1:-1].strip()
        if not inner:
            return []
        raw_tokens = [item.strip() for item in inner.split(",")]
    else:
        raw_tokens = [value]

    tokens: list[str] = []
    for raw_token in raw_tokens:
        if not raw_token or INLINE_TRIGGER_TOKEN_RE.fullmatch(raw_token) is None:
            return None
        tokens.append(normalize_yaml_key(raw_token))
    return tokens


def _job_for_line(lines: list[str], line_index: int) -> str | None:
    for job, start, end in workflow_job_ranges(lines):
        if start < line_index < end:
            return job
    return None


def _workflow_trigger_lines(
    lines: list[str],
) -> tuple[set[int], set[int]]:
    pull_request_target: set[int] = set()
    invalid_inline: set[int] = set()

    for index, raw in enumerate(lines):
        trigger = ON_RE.match(raw)
        if trigger is None or yaml_line_indent(raw) != 0:
            continue

        value = strip_yaml_inline_comment(trigger.group("value")).strip()
        if value:
            tokens = _inline_trigger_tokens(value)
            if tokens is None:
                invalid_inline.add(index)
            elif "pull_request_target" in tokens:
                pull_request_target.add(index)
            continue

        child_indent = yaml_mapping_child_indent(
            lines,
            parent_index=index,
        )
        if child_indent is None:
            continue

        for child_index in range(index + 1, len(lines)):
            child = lines[child_index]
            if not child.strip() or child.lstrip().startswith("#"):
                continue

            indent = yaml_line_indent(child)
            if indent <= 0:
                break

            item = YAML_MAPPING_KEY_RE.match(child)
            if item is None or indent != child_indent:
                continue
            if normalize_yaml_key(item.group("key")) == "pull_request_target":
                pull_request_target.add(child_index)

    return pull_request_target, invalid_inline


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    lines = text.splitlines()
    violations: list[PolicyViolation] = []
    relative = path.as_posix()

    pull_request_target_lines, invalid_inline_trigger_lines = (
        _workflow_trigger_lines(lines)
    )

    for index, raw in enumerate(lines):
        if index in invalid_inline_trigger_lines:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope="workflow",
                    message=(
                        "inline workflow triggers must use literal simple event names "
                        "or a single-line flow sequence of literal event names; "
                        "YAML escapes, tags, block scalars, and multiline flow "
                        "sequences are forbidden"
                    ),
                )
            )

        if index in pull_request_target_lines:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    scope="workflow",
                    message="pull_request_target is forbidden",
                )
            )

        secrets = SECRETS_RE.match(raw)
        if secrets is not None:
            value = strip_yaml_inline_comment(
                secrets.group("value")
            ).strip()
            if value and value != "{}":
                job = _job_for_line(lines, index)
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=index + 1,
                        scope=f"job:{job}" if job is not None else "workflow",
                        message=(
                            "secrets scalar forms (including secrets: inherit) "
                            "are forbidden; map narrow named secrets"
                        ),
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
