from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


PERMISSIONS_RE = re.compile(
    r"^(?P<indent>\s*)permissions:\s*(?P<value>.*?)\s*$"
)
KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*?)\s*$"
)
JOB_RE = re.compile(r"^  (?P<job>[A-Za-z0-9_-]+):\s*(?:#.*)?$")

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
    indent: int,
) -> tuple[dict[str, str], str | None]:
    match = PERMISSIONS_RE.match(lines[index])
    if match is None:
        raise ValueError("permissions parser called on a non-permissions line")

    inline = _unquote(match.group("value"))
    if inline:
        if inline == "{}":
            return {}, "{}"
        return {}, inline

    values: dict[str, str] = {}
    for raw in lines[index + 1 :]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        width = len(raw) - len(raw.lstrip())
        if width <= indent:
            break

        item = KEY_RE.match(raw)
        if item is None:
            continue
        item_indent = _indent_width(item.group("indent"))
        if item_indent != indent + 2:
            continue
        values[item.group("key")] = _unquote(item.group("value"))
    return values, None


def _top_level_permissions(path: Path, lines: list[str]) -> PermissionBlock | None:
    for index, raw in enumerate(lines):
        match = PERMISSIONS_RE.match(raw)
        if match is None or _indent_width(match.group("indent")) != 0:
            continue
        values, inline = _permission_values(lines, index=index, indent=0)
        return PermissionBlock(
            path=path,
            line=index + 1,
            scope="workflow",
            values=values,
            inline=inline,
        )
    return None


def _job_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    jobs_index = -1
    for index, raw in enumerate(lines):
        if raw.strip() == "jobs:" and not raw.startswith((" ", "\t")):
            jobs_index = index
            break
    if jobs_index < 0:
        return []

    starts: list[tuple[str, int]] = []
    for index in range(jobs_index + 1, len(lines)):
        raw = lines[index]
        if raw.strip() and not raw.startswith((" ", "\t")):
            break
        match = JOB_RE.match(raw)
        if match is not None:
            starts.append((match.group("job"), index))

    ranges: list[tuple[str, int, int]] = []
    for position, (job, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else len(lines)
        ranges.append((job, start, end))
    return ranges


def _job_permissions(path: Path, lines: list[str]) -> list[PermissionBlock]:
    blocks: list[PermissionBlock] = []
    for job, start, end in _job_ranges(lines):
        for index in range(start + 1, end):
            raw = lines[index]
            match = PERMISSIONS_RE.match(raw)
            if match is None or _indent_width(match.group("indent")) != 4:
                continue
            values, inline = _permission_values(lines, index=index, indent=4)
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
        raw.strip() == "jobs:" and not raw.startswith((" ", "\t"))
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
        if value != "read":
            violations.append(
                PolicyViolation(
                    path=path,
                    line=workflow.line,
                    scope=workflow.scope,
                    message=(
                        f"top-level permission {permission} must be read-only; "
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
            if value not in {"read", "write"}
        }
        for permission, value in invalid_values.items():
            violations.append(
                PolicyViolation(
                    path=path,
                    line=block.line,
                    scope=block.scope,
                    message=(
                        f"job permission {permission} must be read or write; "
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
