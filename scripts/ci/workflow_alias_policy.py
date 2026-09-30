from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    YAML_KEY_TOKEN,
    normalize_yaml_key,
)


KEY_VALUE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<item>-\s+)?(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*?)\s*$"
)
BLOCK_SCALAR_RE = re.compile(r"^[|>](?:[+-]?[1-9]?|[1-9][+-]?)?$")
# YAML 1.2 anchor names may use non-space punctuation beyond common identifier
# characters. Keep the token grammar broad, but only inspect YAML node positions.
ANCHOR_NAME_TOKEN = r"[^\s,\[\]{}]+"
ANCHOR_ALIAS_RE = re.compile(
    rf"(?:^|[,\[\]{{}}:])\s*(?P<token>[&*]{ANCHOR_NAME_TOKEN})"
    r"(?=$|[\s,\[\]{}])"
)
DIRECT_ANCHOR_ALIAS_RE = re.compile(
    rf"^(?P<token>[&*]{ANCHOR_NAME_TOKEN})(?=$|[\s,\[\]{{}}])"
)


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    token: str
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _strip_comment_and_quoted_content(value: str) -> str:
    result: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    index = 0

    while index < len(value):
        character = value[index]

        if in_double:
            if escaped:
                escaped = False
                result.append(" ")
            elif character == "\\":
                escaped = True
                result.append(" ")
            elif character == '"':
                in_double = False
                result.append(" ")
            else:
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

        if character == '"':
            in_double = True
            result.append(" ")
        elif character == "'":
            in_single = True
            result.append(" ")
        elif character == "#":
            if index == 0 or value[index - 1].isspace():
                result.extend(" " * (len(value) - index))
                break
            result.append(character)
        else:
            result.append(character)
        index += 1

    return "".join(result)


def _direct_alias_or_anchor(value: str) -> str | None:
    stripped = _strip_comment_and_quoted_content(value).strip()
    match = DIRECT_ANCHOR_ALIAS_RE.match(stripped)
    return match.group("token") if match is not None else None


def _structural_tokens(value: str) -> list[str]:
    structural = _strip_comment_and_quoted_content(value).strip()
    return [match.group("token") for match in ANCHOR_ALIAS_RE.finditer(structural)]


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
            key = normalize_yaml_key(key_match.group("key"))
            value = key_match.group("value").strip()
            if BLOCK_SCALAR_RE.fullmatch(value):
                block_scalar_indent = indent
                continue

            if key == "run":
                token = _direct_alias_or_anchor(value)
                if token is None:
                    continue
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=index + 1,
                        token=token,
                        message=(
                            "workflow YAML anchors and aliases are forbidden; "
                            "inline the run command or use an explicit reusable workflow"
                        ),
                    )
                )
                continue

            tokens = _structural_tokens(value)
        else:
            tokens = _structural_tokens(_block_node_payload(raw))

        for token in tokens:
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    token=token,
                    message=(
                        "workflow YAML anchors and aliases are forbidden because "
                        "security policies inspect explicit workflow structure"
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
