from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
import re
from typing import Any


CANONICAL_TAG_PATTERN = '"v[0-9]+.[0-9]+.[0-9]+"'
EXPECTED_WORKFLOW_NAME = "Release Build"
EXPECTED_WORKFLOW_PATH = ".github/workflows/release-build.yml"
EXPECTED_ARTIFACT_NAME = (
    "unsigned-macos-release-${{ github.run_id }}-${{ github.run_attempt }}"
)
EXPECTED_ARCHIVE_PATH = "artifact-payload/release-input/unsigned-macos-app.tar.gz"
EXPECTED_PROVENANCE_PATH = "artifact-payload/release-input/build-provenance.json"
EXPECTED_UPLOAD_PATH = "artifact-payload/"
PRIVILEGED_TOKENS = (
    "MACOS_CERTIFICATE_P12_BASE64",
    "MACOS_CERTIFICATE_PASSWORD",
    "APP_STORE_CONNECT_API_KEY_P8",
    "APP_STORE_CONNECT_KEY_ID",
    "APP_STORE_CONNECT_ISSUER_ID",
    "HOMEBREW_TAP_TOKEN",
    "secrets.",
    "secrets: inherit",
    "reusable-macos-release.yml",
    "reusable-homebrew-update.yml",
)


class WorkflowValidationError(ValueError):
    pass


def decode_github_contents_document(
    document: object,
    *,
    expected_path: str = EXPECTED_WORKFLOW_PATH,
) -> str:
    if not isinstance(document, dict):
        raise WorkflowValidationError("GitHub Contents response must be an object")
    if document.get("type") != "file":
        raise WorkflowValidationError("release build workflow must resolve to a regular file")
    if document.get("path") != expected_path:
        raise WorkflowValidationError(
            f"GitHub Contents path must equal {expected_path!r}"
        )
    blob_sha = document.get("sha")
    if not isinstance(blob_sha, str) or re.fullmatch(r"[0-9a-f]{40}", blob_sha) is None:
        raise WorkflowValidationError(
            "GitHub Contents workflow SHA must be 40 lowercase hexadecimal characters"
        )
    if document.get("encoding") != "base64":
        raise WorkflowValidationError("GitHub Contents workflow encoding must be base64")
    content = document.get("content")
    if not isinstance(content, str) or not content:
        raise WorkflowValidationError("GitHub Contents workflow content must be non-empty")

    normalized_content = "".join(content.split())
    if not normalized_content:
        raise WorkflowValidationError(
            "GitHub Contents workflow content must contain base64 payload"
        )
    try:
        payload = base64.b64decode(normalized_content, validate=True)
    except (binascii.Error, ValueError) as error:
        raise WorkflowValidationError(
            f"GitHub Contents workflow content is not valid base64: {error}"
        ) from error
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise WorkflowValidationError(
            "release build workflow must be valid UTF-8"
        ) from error


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _structural_lines(text: str) -> list[tuple[int, str, str]]:
    lines: list[tuple[int, str, str]] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            lines.append((index, raw, "__TAB_INDENT__"))
            continue
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((index, raw, stripped))
    return lines


def _block(
    lines: list[tuple[int, str, str]],
    start_index: int,
    parent_indent: int,
) -> list[tuple[int, str, str]]:
    result: list[tuple[int, str, str]] = []
    for item in lines[start_index + 1 :]:
        _, raw, _ = item
        if _indent(raw) <= parent_indent:
            break
        result.append(item)
    return result


def _find_top_level(
    lines: list[tuple[int, str, str]],
    key: str,
) -> tuple[int, tuple[int, str, str]] | None:
    expected = f"{key}:"
    for index, item in enumerate(lines):
        _, raw, stripped = item
        if _indent(raw) == 0 and stripped.startswith(expected):
            return index, item
    return None


def _validate_trigger(lines: list[tuple[int, str, str]]) -> list[str]:
    found = _find_top_level(lines, "on")
    if found is None:
        return ["workflow must declare a top-level on: trigger"]
    start, (_, raw, stripped) = found
    if stripped != "on:":
        return ["top-level on trigger must use a block mapping"]

    block = _block(lines, start, _indent(raw))
    event_keys = [
        item
        for item in block
        if _indent(item[1]) == 2 and re.fullmatch(r"[A-Za-z0-9_-]+:", item[2])
    ]
    if [item[2] for item in event_keys] != ["push:"]:
        return ["release build workflow must be triggered only by push"]

    push_index = next(
        (index for index, item in enumerate(block) if _indent(item[1]) == 2 and item[2] == "push:"),
        None,
    )
    if push_index is None:
        return ["release build workflow must declare push trigger"]
    push_block = _block(block, push_index, 2)
    push_keys = [
        item[2]
        for item in push_block
        if _indent(item[1]) == 4 and re.fullmatch(r"[A-Za-z0-9_-]+:", item[2])
    ]
    if push_keys != ["tags:"]:
        return ["release build push trigger must contain only tags"]
    if not any(CANONICAL_TAG_PATTERN in item[2] for item in push_block):
        return [
            "release build tag trigger must include the canonical vX.Y.Z pattern"
        ]
    return []


def _permission_block_errors(
    lines: list[tuple[int, str, str]],
    start_index: int,
    *,
    label: str,
) -> list[str]:
    _, raw, stripped = lines[start_index]
    indent = _indent(raw)
    suffix = stripped.removeprefix("permissions:").strip()
    if suffix:
        if suffix != "{}":
            return [f"{label} permissions must be an empty mapping or a read-only block"]
        return []

    errors: list[str] = []
    block = _block(lines, start_index, indent)
    if not block:
        return [f"{label} permissions block must not be empty"]
    for line_number, child_raw, child in block:
        if _indent(child_raw) != indent + 2:
            continue
        match = re.fullmatch(
            r"([A-Za-z0-9_-]+):\s*(read|none|write)(?:\s+#.*)?",
            child,
        )
        if match is None:
            errors.append(
                f"{label} permissions line {line_number} must be an explicit read/none scalar"
            )
            continue
        if match.group(2) == "write":
            errors.append(
                f"{label} permissions must not grant write access ({match.group(1)})"
            )
    return errors


def _step_uses_errors(lines: list[tuple[int, str, str]]) -> list[str]:
    errors: list[str] = []
    for index, (line_number, raw, stripped) in enumerate(lines):
        match = re.fullmatch(r"uses:\s*(\S+)(?:\s+#.*)?", stripped)
        if match is None:
            continue
        value = match.group(1)
        if value.startswith("./"):
            continue
        action = re.fullmatch(r"([^@\s]+)@([0-9a-f]{40})", value)
        if action is None:
            errors.append(
                f"external action on line {line_number} must be pinned to a full lowercase commit SHA"
            )
            continue

        if action.group(1) == "actions/checkout":
            uses_indent = _indent(raw)
            has_persist_false = False
            for _, next_raw, next_stripped in lines[index + 1 :]:
                next_indent = _indent(next_raw)
                if next_indent < uses_indent:
                    break
                if next_indent == uses_indent and next_stripped.startswith("uses:"):
                    break
                if next_indent == uses_indent - 2 and next_stripped.startswith("- "):
                    break
                if next_stripped == "persist-credentials: false":
                    has_persist_false = True
                    break
            if not has_persist_false:
                errors.append(
                    f"actions/checkout on line {line_number} must set persist-credentials: false"
                )
    return errors


def validate_unprivileged_release_build_workflow(text: str) -> list[str]:
    if not isinstance(text, str) or not text:
        return ["release build workflow text must be non-empty"]

    lines = _structural_lines(text)
    errors: list[str] = []
    for line_number, _, stripped in lines:
        if stripped == "__TAB_INDENT__":
            errors.append(f"workflow indentation must not use tabs (line {line_number})")

    if not any(
        _indent(raw) == 0 and stripped == f"name: {EXPECTED_WORKFLOW_NAME}"
        for _, raw, stripped in lines
    ):
        errors.append(f"workflow name must equal {EXPECTED_WORKFLOW_NAME!r}")

    errors.extend(_validate_trigger(lines))

    top_permissions = [
        (index, item)
        for index, item in enumerate(lines)
        if _indent(item[1]) == 0 and item[2].startswith("permissions:")
    ]
    if len(top_permissions) != 1:
        errors.append("workflow must declare exactly one top-level permissions mapping")
    else:
        index, (_, _, stripped) = top_permissions[0]
        if stripped != "permissions: {}":
            errors.append("workflow-level permissions must equal {}")
        errors.extend(
            _permission_block_errors(lines, index, label="workflow-level")
        )

    jobs_found = _find_top_level(lines, "jobs")
    if jobs_found is None:
        errors.append("workflow must declare jobs")
    else:
        jobs_start, (_, jobs_raw, jobs_stripped) = jobs_found
        if jobs_stripped != "jobs:":
            errors.append("jobs must use a block mapping")
        jobs_block = _block(lines, jobs_start, _indent(jobs_raw))
        job_starts = [
            (index, item)
            for index, item in enumerate(jobs_block)
            if _indent(item[1]) == 2
            and re.fullmatch(r"[A-Za-z0-9_-]+:", item[2])
        ]
        if not job_starts:
            errors.append("workflow must declare at least one job")

        for _, item in job_starts:
            _, job_raw, job_key = item
            job_name = job_key[:-1]
            start_in_jobs = jobs_block.index(item)
            job_block = _block(jobs_block, start_in_jobs, _indent(job_raw))

            if any(
                _indent(raw) == 4 and stripped.startswith("environment:")
                for _, raw, stripped in job_block
            ):
                errors.append(f"job {job_name!r} must not use an Environment")
            if any(
                _indent(raw) == 4 and stripped.startswith("uses:")
                for _, raw, stripped in job_block
            ):
                errors.append(
                    f"job {job_name!r} must not call a reusable workflow"
                )
            if any(
                _indent(raw) == 4 and stripped.startswith("secrets:")
                for _, raw, stripped in job_block
            ):
                errors.append(f"job {job_name!r} must not receive reusable-workflow secrets")

            permission_lines = [
                (index, entry)
                for index, entry in enumerate(job_block)
                if _indent(entry[1]) == 4 and entry[2].startswith("permissions:")
            ]
            if len(permission_lines) > 1:
                errors.append(
                    f"job {job_name!r} must not declare multiple permissions mappings"
                )
            for permission_index, _ in permission_lines:
                errors.extend(
                    _permission_block_errors(
                        job_block,
                        permission_index,
                        label=f"job {job_name!r}",
                    )
                )

    for token in PRIVILEGED_TOKENS:
        if token in text:
            errors.append(f"release build workflow contains forbidden privileged token: {token}")

    if re.search(r"\$\{\{\s*secrets(?:\.|\[)", text):
        errors.append("release build workflow must not reference the secrets context")

    if re.search(r"(?m)^\s*environment\s*:", text):
        errors.append("release build workflow must not declare any Environment")

    errors.extend(_step_uses_errors(lines))

    active_lines = [stripped for _, _, stripped in lines]
    shell_lines = [line[:-1].rstrip() if line.endswith("\\") else line for line in active_lines]

    exact_contract_lines = (
        f"name: {EXPECTED_ARTIFACT_NAME}",
        f"OUTPUT_ARCHIVE: {EXPECTED_ARCHIVE_PATH}",
        f"path: {EXPECTED_UPLOAD_PATH}",
        '--repository "${GITHUB_REPOSITORY}"',
        '--workflow-name "Release Build"',
        '--workflow-path ".github/workflows/release-build.yml"',
        '--run-id "${GITHUB_RUN_ID}"',
        '--run-attempt "${GITHUB_RUN_ATTEMPT}"',
        '--source-event "${GITHUB_EVENT_NAME}"',
        '--source-sha "${GITHUB_SHA}"',
        '--source-ref "${GITHUB_REF}"',
        '--tag "${GITHUB_REF_NAME}"',
        f"--archive-path {EXPECTED_ARCHIVE_PATH}",
        f"--output {EXPECTED_PROVENANCE_PATH}",
    )
    for expected in exact_contract_lines:
        if expected not in shell_lines:
            errors.append(
                f"release build workflow is missing proof contract line: {expected}"
            )

    if not any(
        re.fullmatch(
            r"python3 scripts/release/write-build-provenance\.py",
            line,
        )
        for line in shell_lines
    ):
        errors.append(
            "release build workflow must invoke scripts/release/write-build-provenance.py"
        )

    if not any(
        re.fullmatch(
            r"uses:\s*actions/upload-artifact@[0-9a-f]{40}(?:\s+#.*)?",
            line,
        )
        for line in active_lines
    ):
        errors.append(
            "release build workflow must use a full-SHA-pinned actions/upload-artifact"
        )

    return errors


def load_and_validate_github_contents(path: Path) -> list[str]:
    try:
        with path.open(encoding="utf-8") as handle:
            document: Any = json.load(handle)
        text = decode_github_contents_document(document)
    except (OSError, json.JSONDecodeError, WorkflowValidationError) as error:
        return [str(error)]
    return validate_unprivileged_release_build_workflow(text)
