#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import sys


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
            document = json.load(sys.stdin)
        else:
            document = json.loads(
                args.github_content_json.read_text(encoding="utf-8")
            )
    except (OSError, json.JSONDecodeError) as error:
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

    content = document.get("content")
    if not isinstance(content, str) or not content:
        return fail("GitHub Contents workflow content must be non-empty")

    normalized_content = "".join(content.split())
    if not normalized_content:
        return fail("GitHub Contents workflow content must contain base64 payload")
    try:
        remote_bytes = base64.b64decode(normalized_content, validate=True)
    except (binascii.Error, ValueError) as error:
        return fail(f"GitHub Contents workflow content is not valid base64: {error}")

    try:
        trusted_bytes = args.trusted_workflow.read_bytes()
    except OSError as error:
        return fail(f"unable to read trusted proof workflow: {error}")

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
