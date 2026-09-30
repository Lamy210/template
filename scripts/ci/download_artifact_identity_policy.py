from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


DOWNLOAD_ACTION_RE = re.compile(
    r"^(?P<indent>\s*)(?P<item>-\s+)?uses:\s*['\"]?actions/download-artifact@"
)
STEP_ITEM_RE = re.compile(
    r"^(?P<indent>\s*)-\s+(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$"
)
KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$")


@dataclass(frozen=True)
class DownloadArtifactStep:
    path: Path
    step_name: str
    artifact_ids: str | None
    artifact_name: str | None
    pattern: str | None
    line: int


@dataclass(frozen=True)
class PolicyViolation:
    path: Path
    line: int
    step_name: str
    message: str


def _indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def _step_bounds(lines: list[str], uses_index: int) -> tuple[int, int, str]:
    action_match = DOWNLOAD_ACTION_RE.match(lines[uses_index])
    if action_match is None:
        raise ValueError("internal parser error: uses line does not match download action")

    if action_match.group("item") is not None:
        step_start = uses_index
        step_indent = _indent_width(action_match.group("indent"))
        step_name = "<unnamed download-artifact step>"
    else:
        uses_indent = _indent_width(action_match.group("indent"))
        step_start = -1
        step_indent = -1
        step_name = "<unnamed download-artifact step>"

        for index in range(uses_index - 1, -1, -1):
            match = STEP_ITEM_RE.match(lines[index])
            if match is None:
                continue
            candidate_indent = _indent_width(match.group("indent"))
            if candidate_indent >= uses_indent:
                continue
            step_start = index
            step_indent = candidate_indent
            if match.group("key") == "name" and match.group("value").strip():
                step_name = match.group("value").strip()
            break

        if step_start < 0:
            raise ValueError(
                f"download-artifact at line {uses_index + 1} is outside a workflow step"
            )

    step_end = len(lines)
    for index in range(step_start + 1, len(lines)):
        match = STEP_ITEM_RE.match(lines[index])
        if match is not None and _indent_width(match.group("indent")) == step_indent:
            step_end = index
            break

    return step_start, step_end, step_name


def _with_values(lines: list[str], start: int, end: int) -> dict[str, str]:
    with_index = -1
    with_indent = -1
    for index in range(start, end):
        match = KEY_RE.match(lines[index])
        if match is None or match.group("key") != "with":
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
            values[match.group("key")] = match.group("value").strip()

    return values


def parse_download_artifact_steps(path: Path, text: str) -> list[DownloadArtifactStep]:
    lines = text.splitlines()
    steps: list[DownloadArtifactStep] = []

    for index, line in enumerate(lines):
        if DOWNLOAD_ACTION_RE.match(line) is None:
            continue
        start, end, step_name = _step_bounds(lines, index)
        values = _with_values(lines, index + 1, end)
        steps.append(
            DownloadArtifactStep(
                path=path,
                step_name=step_name,
                artifact_ids=values.get("artifact-ids"),
                artifact_name=values.get("name"),
                pattern=values.get("pattern"),
                line=index + 1,
            )
        )

    return steps


def validate_download_artifact_step(
    step: DownloadArtifactStep,
) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []

    if step.artifact_ids is None or not step.artifact_ids.strip():
        violations.append(
            PolicyViolation(
                path=step.path,
                line=step.line,
                step_name=step.step_name,
                message=(
                    "download-artifact must select immutable artifacts with "
                    "artifact-ids; name/pattern lookup is not allowed"
                ),
            )
        )

    if step.artifact_name is not None:
        violations.append(
            PolicyViolation(
                path=step.path,
                line=step.line,
                step_name=step.step_name,
                message="download-artifact must not include a name selector",
            )
        )

    if step.pattern is not None:
        violations.append(
            PolicyViolation(
                path=step.path,
                line=step.line,
                step_name=step.step_name,
                message="download-artifact must not include a pattern selector",
            )
        )

    return violations


def validate_workflow_text(path: Path, text: str) -> list[PolicyViolation]:
    violations: list[PolicyViolation] = []
    for step in parse_download_artifact_steps(path, text):
        violations.extend(validate_download_artifact_step(step))
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
