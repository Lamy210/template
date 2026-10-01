from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    YAML_BLOCK_SCALAR_HEADER_RE,
    YAML_KEY_TOKEN,
)


KEY_VALUE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<item>-\s+)?(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*?)\s*$"
)


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _strip_non_structural_content(value: str) -> str:
    """Mask quoted scalars, comments, and GitHub expressions while preserving columns."""
    result: list[str] = []
    in_single = False
    in_double = False
    in_expression = False
    escaped = False
    index = 0

    while index < len(value):
        if in_expression:
            if value.startswith("}}", index):
                result.extend((" ", " "))
                index += 2
                in_expression = False
            else:
                result.append(" ")
                index += 1
            continue

        character = value[index]

        if in_double:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_double = False
            result.append(" ")
            index += 1
            continue

        if in_single:
            if character == "'" and index + 1 < len(value) and value[index + 1] == "'":
                result.extend((" ", " "))
                index += 2
                continue
            if character == "'":
                in_single = False
            result.append(" ")
            index += 1
            continue

        if value.startswith("${{", index):
            result.extend((" ", " ", " "))
            index += 3
            in_expression = True
            continue

        if character == '"':
            in_double = True
            result.append(" ")
        elif character == "'":
            in_single = True
            result.append(" ")
        elif character == "#" and (index == 0 or value[index - 1].isspace()):
            result.extend(" " * (len(value) - index))
            break
        else:
            result.append(character)
        index += 1

    return "".join(result)


def _contains_nonempty_flow_mapping(value: str) -> bool:
    structural = _strip_non_structural_content(value)

    for index, character in enumerate(structural):
        if character != "{":
            continue

        previous = index - 1
        while previous >= 0 and structural[previous].isspace():
            previous -= 1
        if previous >= 0 and structural[previous] not in "[,:":
            continue

        following = index + 1
        while following < len(structural) and structural[following].isspace():
            following += 1

        if following < len(structural) and structural[following] == "}":
            continue
        return True

    return False


def _block_node_payload(raw: str) -> str:
    payload = raw.lstrip()
    if len(payload) >= 2 and payload[0] in "-?:" and payload[1].isspace():
        return payload[2:].lstrip()
    return payload


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    lines = text.splitlines()
    violations: list[PolicyViolation] = []
    block_scalar_indent: int | None = None

    for index, raw in enumerate(lines):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = _indent_width(raw) - _indent_width(raw.lstrip())
        if block_scalar_indent is not None:
            if indent > block_scalar_indent:
                continue
            block_scalar_indent = None

        key_match = KEY_VALUE_RE.match(raw)
        if key_match is not None:
            value = key_match.group("value").strip()
            if YAML_BLOCK_SCALAR_HEADER_RE.fullmatch(value):
                block_scalar_indent = indent
                if key_match.group("item") is not None:
                    block_scalar_indent += _indent_width(
                        key_match.group("item")
                    )
                continue
            candidate = value
        else:
            candidate = _block_node_payload(raw)

        if not _contains_nonempty_flow_mapping(candidate):
            continue

        violations.append(
            PolicyViolation(
                path=path,
                line=index + 1,
                message=(
                    "non-empty YAML flow mappings are forbidden in executable workflows; "
                    "use block-style mappings so repository security policies inspect one "
                    "explicit representation"
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
