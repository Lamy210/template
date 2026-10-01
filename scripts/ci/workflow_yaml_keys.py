from __future__ import annotations

import re


YAML_KEY_TOKEN = r'(?:[A-Za-z0-9_-]+|"[A-Za-z0-9_-]+"|\'[A-Za-z0-9_-]+\')'
YAML_BLOCK_SCALAR_HEADER_RE = re.compile(
    r"^[|>](?:[+-]?[1-9]?|[1-9][+-]?)?$"
)
WORKFLOW_JOB_RE = re.compile(rf"^  (?P<job>{YAML_KEY_TOKEN}):\s*(?:#.*)?$")
WORKFLOW_JOBS_RE = re.compile(
    rf"^(?:jobs|\"jobs\"|'jobs'):\s*(?:#.*)?$"
)


def yaml_key_pattern(key: str) -> str:
    escaped = re.escape(key)
    return rf'(?:{escaped}|"{escaped}"|\'{escaped}\')'


def normalize_yaml_key(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def workflow_job_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    jobs_index = -1
    for index, raw in enumerate(lines):
        if WORKFLOW_JOBS_RE.match(raw) is not None and not raw.startswith((" ", "\t")):
            jobs_index = index
            break
    if jobs_index < 0:
        return []

    starts: list[tuple[str, int]] = []
    section_end = len(lines)
    for index in range(jobs_index + 1, len(lines)):
        raw = lines[index]
        if (
            raw.strip()
            and not raw.lstrip().startswith("#")
            and not raw.startswith((" ", "\t"))
        ):
            section_end = index
            break
        match = WORKFLOW_JOB_RE.match(raw)
        if match is not None:
            starts.append((normalize_yaml_key(match.group("job")), index))

    ranges: list[tuple[str, int, int]] = []
    for position, (job, start) in enumerate(starts):
        end = (
            starts[position + 1][1]
            if position + 1 < len(starts)
            else section_end
        )
        ranges.append((job, start, end))
    return ranges
