from __future__ import annotations

import re


YAML_KEY_TOKEN = r'(?:[A-Za-z0-9_-]+|"[A-Za-z0-9_-]+"|\'[A-Za-z0-9_-]+\')'
YAML_BLOCK_SCALAR_HEADER_RE = re.compile(
    r"^[|>](?:[+-]?[1-9]?|[1-9][+-]?)?$"
)
YAML_MAPPING_KEY_RE = re.compile(
    rf"^(?P<indent>\s*)(?P<key>{YAML_KEY_TOKEN}):\s*(?P<value>.*?)\s*$"
)
WORKFLOW_JOBS_RE = re.compile(
    rf"^(?:jobs|\"jobs\"|'jobs'):\s*(?:#.*)?$"
)


def yaml_key_pattern(key: str) -> str:
    escaped = re.escape(key)
    return rf'(?:{escaped}|"{escaped}"|\'{escaped}\')'



def strip_yaml_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    index = 0

    while index < len(value):
        character = value[index]

        if in_double:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_double = False
            index += 1
            continue

        if in_single:
            if (
                character == "'"
                and index + 1 < len(value)
                and value[index + 1] == "'"
            ):
                index += 2
                continue
            if character == "'":
                in_single = False
            index += 1
            continue

        if character == '"':
            in_double = True
        elif character == "'":
            in_single = True
        elif character == "#" and (
            index == 0 or value[index - 1].isspace()
        ):
            return value[:index].rstrip()

        index += 1

    return value.rstrip()

def normalize_yaml_key(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def yaml_indent_width(value: str) -> int:
    return len(value.replace("\t", "    "))


def yaml_line_indent(raw: str) -> int:
    return yaml_indent_width(raw) - yaml_indent_width(raw.lstrip())


def yaml_mapping_child_indent(
    lines: list[str],
    *,
    parent_index: int,
    end: int | None = None,
) -> int | None:
    parent_indent = yaml_line_indent(lines[parent_index])
    limit = len(lines) if end is None else end
    child_indent: int | None = None

    for index in range(parent_index + 1, limit):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        indent = yaml_line_indent(raw)
        if indent <= parent_indent:
            break

        if YAML_MAPPING_KEY_RE.match(raw) is None:
            continue
        if child_indent is None or indent < child_indent:
            child_indent = indent

    return child_indent


def yaml_mapping_key_indent(indent: str, item: str | None) -> int:
    width = yaml_indent_width(indent)
    if item is not None:
        width += yaml_indent_width(item)
    return width


def yaml_sequence_item_end(
    lines: list[str],
    *,
    start: int,
    item_indent: int,
) -> int:
    for index in range(start + 1, len(lines)):
        raw = lines[index]
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = yaml_line_indent(raw)
        if indent <= item_indent:
            return index
    return len(lines)


def workflow_job_ranges(lines: list[str]) -> list[tuple[str, int, int]]:
    jobs_index = -1
    for index, raw in enumerate(lines):
        if WORKFLOW_JOBS_RE.match(raw) is not None and not raw.startswith((" ", "\t")):
            jobs_index = index
            break
    if jobs_index < 0:
        return []

    section_end = len(lines)
    for index in range(jobs_index + 1, len(lines)):
        raw = lines[index]
        if (
            raw.strip()
            and not raw.lstrip().startswith("#")
            and yaml_line_indent(raw) == 0
        ):
            section_end = index
            break

    job_indent = yaml_mapping_child_indent(
        lines,
        parent_index=jobs_index,
        end=section_end,
    )
    if job_indent is None:
        return []

    starts: list[tuple[str, int]] = []
    for index in range(jobs_index + 1, section_end):
        raw = lines[index]
        match = YAML_MAPPING_KEY_RE.match(raw)
        if match is None or yaml_line_indent(raw) != job_indent:
            continue
        starts.append((normalize_yaml_key(match.group("key")), index))

    ranges: list[tuple[str, int, int]] = []
    for position, (job, start) in enumerate(starts):
        end = (
            starts[position + 1][1]
            if position + 1 < len(starts)
            else section_end
        )
        ranges.append((job, start, end))
    return ranges
