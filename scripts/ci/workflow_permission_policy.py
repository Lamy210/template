from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from scripts.ci.workflow_yaml_keys import (
    YAML_KEY_TOKEN,
    normalize_yaml_key,
    workflow_job_ranges,
    yaml_key_pattern,
    yaml_line_indent,
    yaml_mapping_child_indent,
)


PERMISSIONS_RE = re.compile(
    rf"^(?P<indent>\s*){yaml_key_pattern('permissions')}:\s*(?P<value>.*?)\s*$"
)
KEY_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*?)\s*$"
)
JOBS_RE = re.compile(rf"^{yaml_key_pattern('jobs')}:\s*(?:#.*)?$")

ALLOWED_WRITE_PERMISSIONS: dict[tuple[str, str], dict[str, str]] = {
    (
        ".github/workflows/reusable-macos-release.yml",
        "publish",
    ): {
        "actions": "read",
        "contents": "write",
    },
    (
        "examples/app-release-publisher.yml",
        "sign-and-publish",
    ): {
        "actions": "read",
        "contents": "write",
    },
}


@dataclass(frozen=True)
class PermissionBlock:
    path: Path
    line: int
    scope: str
    values: dict[str, str]
    inline: str | None


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    scope: str
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


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


def _permission_values(
    lines: list[str],
    *,
    index: int,
    end: int | None = None,
) -> tuple[dict[str, str], str | None]:
    match = PERMISSIONS_RE.match(lines[index])
    if match is None:
        raise ValueError("permissions parser called on a non-permissions line")

    inline = _unquote(match.group("value"))
    if inline:
        if inline == "{}":
            return {}, "{}"
        return {}, inline

    parent_indent = yaml_line_indent(lines[index])
    limit = len(lines) if end is None else end
    child_indent = yaml_mapping_child_indent(
        lines,
        parent_index=index,
        end=limit,
    )
    if child_indent is None:
        return {}, None

    values: dict[str, str] = {}
    for raw in lines[index + 1 : limit]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        width = yaml_line_indent(raw)
        if width <= parent_indent:
            break

        item = KEY_RE.match(raw)
        if item is None or width != child_indent:
            continue
        values[normalize_yaml_key(item.group("key"))] = _unquote(item.group("value"))
    return values, None


def _top_level_permissions(path: Path, lines: list[str]) -> PermissionBlock | None:
    for index, raw in enumerate(lines):
        match = PERMISSIONS_RE.match(raw)
        if match is None or _indent_width(match.group("indent")) != 0:
            continue
        values, inline = _permission_values(lines, index=index)
        return PermissionBlock(
            path=path,
            line=index + 1,
            scope="workflow",
            values=values,
            inline=inline,
        )
    return None


def _job_permissions(path: Path, lines: list[str]) -> list[PermissionBlock]:
    blocks: list[PermissionBlock] = []
    for job, start, end in workflow_job_ranges(lines):
        property_indent = yaml_mapping_child_indent(
            lines,
            parent_index=start,
            end=end,
        )
        if property_indent is None:
            continue

        for index in range(start + 1, end):
            raw = lines[index]
            match = PERMISSIONS_RE.match(raw)
            if match is None or yaml_line_indent(raw) != property_indent:
                continue
            values, inline = _permission_values(
                lines,
                index=index,
                end=end,
            )
            blocks.append(
                PermissionBlock(
                    path=path,
                    line=index + 1,
                    scope=f"job:{job}",
                    values=values,
                    inline=inline,
                )
            )
            break
    return blocks


def parse_permission_blocks(path: Path, text: str) -> list[PermissionBlock]:
    lines = text.splitlines()
    blocks: list[PermissionBlock] = []
    top = _top_level_permissions(path, lines)
    if top is not None:
        blocks.append(top)
    blocks.extend(_job_permissions(path, lines))
    return blocks


def _is_workflow_document(text: str) -> bool:
    lines = text.splitlines()
    has_jobs = any(
        JOBS_RE.match(raw) is not None and not raw.startswith((" ", "\t"))
        for raw in lines
    )
    has_trigger = any(
        raw.startswith("on:")
        or raw.startswith('"on":')
        or raw.startswith("'on':")
        for raw in lines
    )
    return has_jobs and has_trigger


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    blocks = parse_permission_blocks(path, text)
    workflow = next((item for item in blocks if item.scope == "workflow"), None)

    if workflow is None:
        return [
            PolicyViolation(
                path=path,
                line=1,
                scope="workflow",
                message="workflow must declare explicit top-level permissions",
            )
        ]

    if workflow.inline not in {None, "{}"}:
        violations.append(
            PolicyViolation(
                path=path,
                line=workflow.line,
                scope=workflow.scope,
                message=(
                    "top-level permissions must be an explicit mapping or {}; "
                    "read-all/write-all/expressions are not allowed"
                ),
            )
        )
    for permission, value in workflow.values.items():
        if value not in {"read", "none"}:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=workflow.line,
                    scope=workflow.scope,
                    message=(
                        f"top-level permission {permission} must be read/none; "
                        f"found {value!r}"
                    ),
                )
            )

    relative = path.as_posix()
    for block in blocks:
        if not block.scope.startswith("job:"):
            continue
        job = block.scope.removeprefix("job:")
        expected_write = ALLOWED_WRITE_PERMISSIONS.get((relative, job))

        if block.inline not in {None, "{}"}:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=block.line,
                    scope=block.scope,
                    message=(
                        "job permissions must be an explicit mapping or {}; "
                        "read-all/write-all/expressions are not allowed"
                    ),
                )
            )
            continue

        writes = {
            permission: value
            for permission, value in block.values.items()
            if value == "write"
        }
        invalid_values = {
            permission: value
            for permission, value in block.values.items()
            if value not in {"read", "write", "none"}
        }
        for permission, value in invalid_values.items():
            violations.append(
                PolicyViolation(
                    path=path,
                    line=block.line,
                    scope=block.scope,
                    message=(
                        f"job permission {permission} must be read, write, or none; "
                        f"found {value!r}"
                    ),
                )
            )

        if writes:
            if expected_write is None:
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=block.line,
                        scope=block.scope,
                        message=(
                            "job write permissions are forbidden outside the "
                            "explicit release-publication allowlist"
                        ),
                    )
                )
            elif block.values != expected_write:
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=block.line,
                        scope=block.scope,
                        message=(
                            "allowlisted release-publication permissions must equal "
                            f"{expected_write!r}; found {block.values!r}"
                        ),
                    )
                )
        elif expected_write is not None:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=block.line,
                    scope=block.scope,
                    message=(
                        "allowlisted release-publication job must retain its exact "
                        f"permission set {expected_write!r}"
                    ),
                )
            )

    for (allowed_path, allowed_job), expected in ALLOWED_WRITE_PERMISSIONS.items():
        if relative != allowed_path:
            continue
        block = next(
            (
                item
                for item in blocks
                if item.scope == f"job:{allowed_job}"
            ),
            None,
        )
        if block is None:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=1,
                    scope=f"job:{allowed_job}",
                    message=(
                        "release-publication permission allowlist target is missing "
                        f"or lacks explicit permissions {expected!r}"
                    ),
                )
            )

    return violations


def workflow_paths(root: Path) -> Iterable[Path]:
    workflow_dir = root / ".github/workflows"
    if workflow_dir.is_dir():
        for pattern in ("*.yml", "*.yaml"):
            yield from sorted(workflow_dir.glob(pattern))

    examples = root / "examples"
    if examples.is_dir():
        for pattern in ("*.yml", "*.yaml"):
            for path in sorted(examples.rglob(pattern)):
                text = path.read_text(encoding="utf-8")
                if _is_workflow_document(text):
                    yield path


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
