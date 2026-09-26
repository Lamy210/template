from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.post_split_proof_evidence import EvidenceError, build_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts/release/post_split_proof_evidence.py"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"


def valid_kwargs() -> dict[str, object]:
    return {
        "repository": "example/disposable",
        "default_branch": "main",
        "tag": "v0.0.1",
        "source_ref": "post-split-ancestor",
        "source_sha": SOURCE_SHA,
        "source_run_id": 101,
        "source_run_attempt": 1,
        "publisher_sha": PUBLISHER_SHA,
        "publisher_run_id": 202,
        "publisher_run_attempt": 2,
    }


class PostSplitProofEvidenceTests(unittest.TestCase):
    def test_builds_closed_deterministic_identity_document(self) -> None:
        evidence = build_evidence(**valid_kwargs())

        self.assertEqual(
            {
                "defaultBranch": "main",
                "proofType": "post-split-ancestor-runtime",
                "publisherRunAttempt": 2,
                "publisherRunId": 202,
                "publisherSHA": PUBLISHER_SHA,
                "repository": "example/disposable",
                "schemaVersion": 1,
                "sourceRef": "post-split-ancestor",
                "sourceRunAttempt": 1,
                "sourceRunId": 101,
                "sourceSHA": SOURCE_SHA,
                "tag": "v0.0.1",
            },
            evidence,
        )

    def test_rejects_invalid_identity_fields(self) -> None:
        mutations = (
            ("repository", "bad"),
            ("tag", "v01.0.0"),
            ("source_ref", "bad ref"),
            ("source_sha", "A" * 40),
            ("publisher_sha", SOURCE_SHA),
            ("source_run_id", 0),
            ("source_run_attempt", True),
            ("publisher_run_id", -1),
            ("publisher_run_attempt", 0),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                kwargs = valid_kwargs()
                kwargs[field] = value
                with self.assertRaises(EvidenceError):
                    build_evidence(**kwargs)

    def test_cli_writes_once_without_timestamp_or_ambient_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proof.json"
            args = [
                sys.executable,
                str(SCRIPT),
                "--output",
                str(output),
                "--repository",
                "example/disposable",
                "--default-branch",
                "main",
                "--tag",
                "v0.0.1",
                "--source-ref",
                "post-split-ancestor",
                "--source-sha",
                SOURCE_SHA,
                "--source-run-id",
                "101",
                "--source-run-attempt",
                "1",
                "--publisher-sha",
                PUBLISHER_SHA,
                "--publisher-run-id",
                "202",
                "--publisher-run-attempt",
                "2",
            ]
            first = subprocess.run(
                args,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            second = subprocess.run(
                args,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            document = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(2, second.returncode)
        self.assertIn("already exists", second.stderr)
        self.assertEqual("post-split-ancestor-runtime", document["proofType"])
        self.assertNotIn("timestamp", document)
        self.assertNotIn("createdAt", document)


if __name__ == "__main__":
    unittest.main()
