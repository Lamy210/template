#!/usr/bin/env python3
"""Write deterministic evidence for a successful post-split ancestor runtime proof."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TAG_RE = re.compile(r"^v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


class EvidenceError(ValueError):
    pass


def _positive_int(value: int, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise EvidenceError(f"{label} must be a positive integer")
    return value


def build_evidence(
    *,
    repository: str,
    default_branch: str,
    tag: str,
    source_ref: str,
    source_sha: str,
    source_run_id: int,
    source_run_attempt: int,
    publisher_sha: str,
    publisher_run_id: int,
    publisher_run_attempt: int,
) -> dict[str, object]:
    if REPOSITORY_RE.fullmatch(repository) is None:
        raise EvidenceError("repository must be owner/repo")
    if not default_branch or "\n" in default_branch or "\r" in default_branch:
        raise EvidenceError("default branch must be a non-empty single-line value")
    if REF_RE.fullmatch(source_ref) is None:
        raise EvidenceError("source ref contains unsupported characters")
    if TAG_RE.fullmatch(tag) is None:
        raise EvidenceError("tag must be canonical stable SemVer")
    if SHA_RE.fullmatch(source_sha) is None:
        raise EvidenceError("source SHA must be 40 lowercase hexadecimal characters")
    if SHA_RE.fullmatch(publisher_sha) is None:
        raise EvidenceError("publisher SHA must be 40 lowercase hexadecimal characters")
    if source_sha == publisher_sha:
        raise EvidenceError("source SHA must differ from publisher SHA")

    return {
        "defaultBranch": default_branch,
        "proofType": "post-split-ancestor-runtime",
        "publisherRunAttempt": _positive_int(
            publisher_run_attempt, "publisher run attempt"
        ),
        "publisherRunId": _positive_int(publisher_run_id, "publisher run id"),
        "publisherSHA": publisher_sha,
        "repository": repository,
        "schemaVersion": 1,
        "sourceRef": source_ref,
        "sourceRunAttempt": _positive_int(source_run_attempt, "source run attempt"),
        "sourceRunId": _positive_int(source_run_id, "source run id"),
        "sourceSHA": source_sha,
        "tag": tag,
    }


def write_evidence(path: Path, evidence: dict[str, object]) -> None:
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise EvidenceError(f"evidence output already exists: {path}") from exc
    except OSError as exc:
        raise EvidenceError(f"cannot write evidence output {path}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--source-run-attempt", required=True, type=int)
    parser.add_argument("--publisher-sha", required=True)
    parser.add_argument("--publisher-run-id", required=True, type=int)
    parser.add_argument("--publisher-run-attempt", required=True, type=int)
    args = parser.parse_args()

    try:
        evidence = build_evidence(
            repository=args.repository,
            default_branch=args.default_branch,
            tag=args.tag,
            source_ref=args.source_ref,
            source_sha=args.source_sha,
            source_run_id=args.source_run_id,
            source_run_attempt=args.source_run_attempt,
            publisher_sha=args.publisher_sha,
            publisher_run_id=args.publisher_run_id,
            publisher_run_attempt=args.publisher_run_attempt,
        )
        write_evidence(args.output, evidence)
    except EvidenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
