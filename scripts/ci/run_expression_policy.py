from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ci.workflow_permission_policy import workflow_paths
from scripts.ci.workflow_yaml_keys import (
    YAML_BLOCK_SCALAR_HEADER_RE,
    yaml_key_pattern,
    yaml_mapping_key_indent,
)


RUN_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<item>-\s+)?{yaml_key_pattern('run')}:\s*(?P<value>.*?)\s*$"
)
EXPRESSION_RE = re.compile(r"\$\{\{")


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
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


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    lines = text.splitlines()
    violations: list[PolicyViolation] = []

    for index, raw in enumerate(lines):
        match = RUN_RE.match(raw)
        if match is None:
            continue

        run_indent = yaml_mapping_key_indent(
            match.group("indent"),
            match.group("item"),
        )
        value = _strip_inline_comment(match.group("value")).strip()

        if value and YAML_BLOCK_SCALAR_HEADER_RE.fullmatch(value) is None:
            if EXPRESSION_RE.search(value):
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=index + 1,
                        message=(
                            "run command must not interpolate GitHub expressions "
                            "directly; route expression values through env"
                        ),
                    )
                )
            continue

        for body_index in range(index + 1, len(lines)):
            body = lines[body_index]
            if body.strip():
                body_indent = _indent_width(body) - _indent_width(body.lstrip())
                if body_indent <= run_indent:
                    break
            if EXPRESSION_RE.search(body):
                violations.append(
                    PolicyViolation(
                        path=path,
                        line=body_index + 1,
                        message=(
                            "run block must not interpolate GitHub expressions "
                            "directly; route expression values through env"
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
