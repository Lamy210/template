from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    YAML_BLOCK_SCALAR_HEADER_RE,
    YAML_KEY_TOKEN,
    yaml_mapping_key_indent,
)


KEY_VALUE_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<item>-\s+)?(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*?)\s*$"
)
QUOTED_MAPPING_KEY_RE = re.compile(
    r"^(?P<indent>\s*)(?P<item>-\s+)?"
    r'(?P<key>"(?:\\.|[^"\\])*"|\'(?:\'\'|[^\'])*\')'
    r"\s*:"
)
CANONICAL_QUOTED_KEY_RE = re.compile(
    r'^(?:"[A-Za-z0-9_-]+"|\'[A-Za-z0-9_-]+\')$'
)


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    key: str
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _structural_payload(raw: str) -> str:
    payload = raw.lstrip()
    if payload.startswith("- "):
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

        payload = _structural_payload(raw)
        if (
            payload == "?"
            or payload.startswith("? ")
            or payload.startswith("!")
        ):
            violations.append(
                PolicyViolation(
                    path=path,
                    line=index + 1,
                    key=payload,
                    message=(
                        "explicit YAML mapping-key syntax and YAML tags are "
                        "forbidden in executable workflow structure; spell mapping "
                        "keys directly so security policies inspect one canonical "
                        "representation"
                    ),
                )
            )
            continue

        canonical_key = KEY_VALUE_RE.match(raw)
        if canonical_key is not None:
            value = canonical_key.group("value").strip()
            if YAML_BLOCK_SCALAR_HEADER_RE.fullmatch(value):
                block_scalar_indent = yaml_mapping_key_indent(
                    canonical_key.group("indent"),
                    canonical_key.group("item"),
                )

        quoted = QUOTED_MAPPING_KEY_RE.match(raw)
        if quoted is None:
            continue

        key = quoted.group("key")
        if CANONICAL_QUOTED_KEY_RE.fullmatch(key) is not None:
            continue

        violations.append(
            PolicyViolation(
                path=path,
                line=index + 1,
                key=key,
                message=(
                    "quoted workflow mapping keys must spell a simple ASCII key "
                    "literally; YAML escapes and complex quoted keys are forbidden "
                    "so security policies inspect one canonical key representation"
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
