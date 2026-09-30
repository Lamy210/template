from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

from scripts.ci.workflow_yaml_keys import (
    YAML_KEY_TOKEN,
    normalize_yaml_key,
    yaml_key_pattern,
)


USES_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<item>-\s+)?{yaml_key_pattern('uses')}:\s*(?P<value>.+?)\s*$"
)
STEP_ITEM_RE = re.compile(
    rf"^(?P<indent>\s*)-\s+(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*)$"
)
KEY_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*)$"
)
FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXTERNAL_USE_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?P<subpath>/[^@]+)?@(?P<ref>[^\s]+)$"
)


@dataclass(frozen=True)
class ActionUse:
    path: Path
    line: int
    step_name: str
    value: str
    with_values: dict[str, str]


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    step_name: str
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


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


def _step_context(
    lines: list[str], uses_index: int
) -> tuple[int, int, str] | None:
    match = USES_RE.match(lines[uses_index])
    if match is None:
        return None

    uses_indent = _indent_width(match.group("indent"))
    if match.group("item") is not None:
        return uses_index, len(lines), "<unnamed action step>"

    start = -1
    step_indent = -1
    step_name = "<workflow/job-level use>"
    for index in range(uses_index - 1, -1, -1):
        item = STEP_ITEM_RE.match(lines[index])
        if item is None:
            continue
        candidate_indent = _indent_width(item.group("indent"))
        if candidate_indent >= uses_indent:
            continue
        start = index
        step_indent = candidate_indent
        if normalize_yaml_key(item.group("key")) == "name" and item.group("value").strip():
            step_name = item.group("value").strip()
        break

    if start < 0:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        item = STEP_ITEM_RE.match(lines[index])
        if item is not None and _indent_width(item.group("indent")) == step_indent:
            end = index
            break
    return start, end, step_name


def _with_values(lines: list[str], start: int, end: int) -> dict[str, str]:
    with_index = -1
    with_indent = -1
    for index in range(start, end):
        match = KEY_RE.match(lines[index])
        if match is None or normalize_yaml_key(match.group("key")) != "with":
            continue
        with_index = index
        with_indent = _indent_width(match.group("indent"))
        break

    if with_index < 0:
        return {}

    values: dict[str, str] = {}
    for index in range(with_index + 1, end):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = KEY_RE.match(raw)
        if match is None:
            continue
        indent = _indent_width(match.group("indent"))
        if indent <= with_indent:
            break
        if indent == with_indent + 2:
            values[normalize_yaml_key(match.group("key"))] = _unquote(
                _strip_inline_comment(match.group("value"))
            )
    return values


def parse_action_uses(path: Path, text: str) -> list[ActionUse]:
    lines = text.splitlines()
    uses: list[ActionUse] = []

    for index, raw in enumerate(lines):
        match = USES_RE.match(raw)
        if match is None:
            continue
        value = _unquote(_strip_inline_comment(match.group("value")))
        context = _step_context(lines, index)
        if context is None:
            uses.append(
                ActionUse(
                    path=path,
                    line=index + 1,
                    step_name="<workflow/job-level use>",
                    value=value,
                    with_values={},
                )
            )
            continue
        start, end, step_name = context
        uses.append(
            ActionUse(
                path=path,
                line=index + 1,
                step_name=step_name,
                value=value,
                with_values=_with_values(lines, index + 1, end),
            )
        )
    return uses


def validate_action_use(action: ActionUse) -> list[PolicyViolation]:
    if action.value.startswith("./") or action.value.startswith("$/"):
        return []

    external = EXTERNAL_USE_RE.fullmatch(action.value)
    if external is None:
        return [
            PolicyViolation(
                path=action.path,
                line=action.line,
                step_name=action.step_name,
                message=(
                    "external uses must be owner/repository[/subpath]@<40-char lowercase SHA> "
                    "or a local repository path"
                ),
            )
        ]

    violations: list[PolicyViolation] = []
    if FULL_SHA_RE.fullmatch(external.group("ref")) is None:
        violations.append(
            PolicyViolation(
                path=action.path,
                line=action.line,
                step_name=action.step_name,
                message=(
                    "external GitHub Action/reusable workflow must be pinned "
                    "to a full lowercase commit SHA"
                ),
            )
        )

    if (
        external.group("owner").casefold() == "actions"
        and external.group("repo").casefold() == "checkout"
    ):
        persist = action.with_values.get("persist-credentials")
        if persist is None or persist.strip().lower() != "false":
            violations.append(
                PolicyViolation(
                    path=action.path,
                    line=action.line,
                    step_name=action.step_name,
                    message="actions/checkout must set persist-credentials: false",
                )
            )

    return violations


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for action in parse_action_uses(path, text):
        violations.extend(validate_action_use(action))
    return violations


def workflow_paths(root: Path) -> Iterable[Path]:
    for directory in (root / ".github", root / "examples"):
        if not directory.is_dir():
            continue
        for pattern in ("*.yml", "*.yaml"):
            yield from sorted(directory.rglob(pattern))


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
