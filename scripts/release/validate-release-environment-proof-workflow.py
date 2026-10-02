#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.release.proof_workflow_input import (  # noqa: E402
    ProofWorkflowInputError,
    decode_bounded_workflow_base64,
    load_bounded_github_contents_file,
    load_bounded_github_contents_stream,
    read_bounded_trusted_workflow,
)


def fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Require the remote disposable release Environment proof workflow "
            "to exactly match the trusted local example."
        )
    )
    parser.add_argument("--github-content-json", type=Path)
    parser.add_argument("--expected-path", required=True)
    parser.add_argument("--trusted-workflow", required=True, type=Path)
    args = parser.parse_args()

    try:
        if args.github_content_json is None:
            document = load_bounded_github_contents_stream(sys.stdin.buffer)
        else:
            document = load_bounded_github_contents_file(
                args.github_content_json
            )
    except ProofWorkflowInputError as error:
        return fail(f"unable to read GitHub Contents response: {error}")

    if not isinstance(document, dict):
        return fail("GitHub Contents response must be an object")
    if document.get("type") != "file":
        return fail("proof workflow must resolve to a regular file")
    if document.get("path") != args.expected_path:
        return fail(
            f"GitHub Contents path must equal {args.expected_path!r}"
        )

    blob_sha = document.get("sha")
    if not isinstance(blob_sha, str) or re.fullmatch(r"[0-9a-f]{40}", blob_sha) is None:
        return fail(
            "GitHub Contents workflow SHA must be 40 lowercase hexadecimal characters"
        )
    if document.get("encoding") != "base64":
        return fail("GitHub Contents workflow encoding must be base64")

    try:
        remote_bytes = decode_bounded_workflow_base64(
            document.get("content")
        )
        trusted_bytes = read_bounded_trusted_workflow(
            args.trusted_workflow
        )
    except ProofWorkflowInputError as error:
        return fail(str(error))

    if remote_bytes != trusted_bytes:
        remote_digest = hashlib.sha256(remote_bytes).hexdigest()
        trusted_digest = hashlib.sha256(trusted_bytes).hexdigest()
        return fail(
            "remote release Environment proof workflow does not exactly match "
            f"trusted example: remote_sha256={remote_digest} "
            f"trusted_sha256={trusted_digest}"
        )

    print("remote release Environment proof workflow matches trusted example")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
