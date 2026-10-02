from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import BinaryIO

from scripts.release.secure_file_snapshot import (
    RegularFileSnapshotError,
    snapshot_regular_file,
)


MAX_PROOF_WORKFLOW_BYTES = 1024 * 1024
MAX_GITHUB_CONTENTS_JSON_BYTES = 2 * 1024 * 1024


class ProofWorkflowInputError(RuntimeError):
    pass


def _parse_json_bytes(payload: bytes) -> object:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ProofWorkflowInputError(
            "GitHub Contents response must be valid UTF-8"
        ) from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ProofWorkflowInputError(
            f"GitHub Contents response is invalid JSON: {error}"
        ) from error


def load_bounded_github_contents_file(path: Path) -> object:
    try:
        with snapshot_regular_file(
            path,
            prefix="proof-github-contents.",
            max_bytes=MAX_GITHUB_CONTENTS_JSON_BYTES,
        ) as snapshot:
            payload = snapshot.read_bytes()
    except RegularFileSnapshotError as error:
        raise ProofWorkflowInputError(str(error)) from error
    except OSError as error:
        raise ProofWorkflowInputError(
            f"unable to read GitHub Contents response: {error}"
        ) from error
    return _parse_json_bytes(payload)


def load_bounded_github_contents_stream(stream: BinaryIO) -> object:
    try:
        payload = stream.read(MAX_GITHUB_CONTENTS_JSON_BYTES + 1)
    except OSError as error:
        raise ProofWorkflowInputError(
            f"unable to read GitHub Contents response: {error}"
        ) from error
    if len(payload) > MAX_GITHUB_CONTENTS_JSON_BYTES:
        raise ProofWorkflowInputError(
            "GitHub Contents response exceeds byte limit: "
            f"{len(payload)} > {MAX_GITHUB_CONTENTS_JSON_BYTES}"
        )
    return _parse_json_bytes(payload)


def decode_bounded_workflow_base64(content: object) -> bytes:
    if not isinstance(content, str) or not content:
        raise ProofWorkflowInputError(
            "GitHub Contents workflow content must be non-empty"
        )

    normalized = "".join(content.split())
    if not normalized:
        raise ProofWorkflowInputError(
            "GitHub Contents workflow content must contain base64 payload"
        )
    try:
        payload = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ProofWorkflowInputError(
            f"GitHub Contents workflow content is not valid base64: {error}"
        ) from error
    if len(payload) > MAX_PROOF_WORKFLOW_BYTES:
        raise ProofWorkflowInputError(
            "decoded proof workflow exceeds byte limit: "
            f"{len(payload)} > {MAX_PROOF_WORKFLOW_BYTES}"
        )
    return payload


def read_bounded_trusted_workflow(path: Path) -> bytes:
    try:
        with snapshot_regular_file(
            path,
            prefix="trusted-proof-workflow.",
            max_bytes=MAX_PROOF_WORKFLOW_BYTES,
        ) as snapshot:
            return snapshot.read_bytes()
    except RegularFileSnapshotError as error:
        raise ProofWorkflowInputError(str(error)) from error
    except OSError as error:
        raise ProofWorkflowInputError(
            f"unable to read trusted proof workflow: {error}"
        ) from error


__all__ = [
    "MAX_GITHUB_CONTENTS_JSON_BYTES",
    "MAX_PROOF_WORKFLOW_BYTES",
    "ProofWorkflowInputError",
    "decode_bounded_workflow_base64",
    "load_bounded_github_contents_file",
    "load_bounded_github_contents_stream",
    "read_bounded_trusted_workflow",
]
