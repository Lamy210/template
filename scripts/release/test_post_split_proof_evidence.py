from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from scripts.release.post_split_proof_evidence import (
    EvidenceError,
    build_evidence,
    write_evidence,
)


REPO_ID = 1367784801
REPOSITORY = "example/template"
SOURCE_SHA = "0123456789abcdef0123456789abcdef01234567"
PUBLISHER_SHA = "1123456789abcdef0123456789abcdef01234567"
SOURCE_RUN_ID = 101
SOURCE_RUN_ATTEMPT = 1
PUBLISHER_RUN_ID = 202
PUBLISHER_RUN_ATTEMPT = 2
VALIDATOR_ARTIFACT_ID = 303
VALIDATOR_ARTIFACT_DIGEST = "sha256:" + "c" * 64
SOURCE_ARTIFACT_ID = 404
SOURCE_ARTIFACT_DIGEST = "sha256:" + "a" * 64
ARCHIVE_DIGEST = "sha256:" + "b" * 64


def inputs() -> dict[str, object]:
    return {
        "repository": {
            "id": REPO_ID,
            "full_name": REPOSITORY,
            "default_branch": "main",
        },
        "default_commit": {"sha": PUBLISHER_SHA},
        "final_default_commit": {"sha": PUBLISHER_SHA},
        "source_run": {
            "id": SOURCE_RUN_ID,
            "run_attempt": SOURCE_RUN_ATTEMPT,
            "name": "Release Build",
            "path": ".github/workflows/release-build.yml",
            "head_branch": "v1.2.3",
            "head_sha": SOURCE_SHA,
        },
        "publisher_run": {
            "id": PUBLISHER_RUN_ID,
            "run_attempt": PUBLISHER_RUN_ATTEMPT,
            "name": "Release Publisher",
            "path": ".github/workflows/release-publisher.yml",
            "head_sha": PUBLISHER_SHA,
        },
        "artifacts": [
            {
                "id": VALIDATOR_ARTIFACT_ID,
                "name": (
                    f"validated-release-input-{PUBLISHER_RUN_ID}-"
                    f"{PUBLISHER_RUN_ATTEMPT}-{SOURCE_RUN_ID}-{SOURCE_RUN_ATTEMPT}"
                ),
                "digest": VALIDATOR_ARTIFACT_DIGEST,
            }
        ],
        "metadata": {
            "sourceArtifactId": SOURCE_ARTIFACT_ID,
            "sourceArtifactDigest": SOURCE_ARTIFACT_DIGEST,
            "archiveSha256": ARCHIVE_DIGEST,
            "appBasename": "MyApp.app",
            "bundleId": "com.example.MyApp",
            "version": "1.2.3",
        },
        "archive_digest": ARCHIVE_DIGEST,
        "comparison": {
            "status": "ahead",
            "ahead_by": 7,
            "behind_by": 0,
            "merge_base_commit": {"sha": SOURCE_SHA},
        },
    }


class PostSplitProofEvidenceTests(unittest.TestCase):
    def test_builds_closed_deterministic_verified_evidence(self) -> None:
        evidence = build_evidence(**inputs())

        self.assertEqual(
            {
                "ancestor": {
                    "aheadBy": 7,
                    "behindBy": 0,
                    "mergeBaseSHA": SOURCE_SHA,
                    "status": "ahead",
                },
                "application": {
                    "appBasename": "MyApp.app",
                    "bundleId": "com.example.MyApp",
                    "version": "1.2.3",
                },
                "defaultHead": {
                    "finalSHA": PUBLISHER_SHA,
                    "initialSHA": PUBLISHER_SHA,
                },
                "proofType": "post-split-ancestor-runtime",
                "publisher": {
                    "runAttempt": PUBLISHER_RUN_ATTEMPT,
                    "runId": PUBLISHER_RUN_ID,
                    "sha": PUBLISHER_SHA,
                    "validatorArtifactDigest": VALIDATOR_ARTIFACT_DIGEST,
                    "validatorArtifactId": VALIDATOR_ARTIFACT_ID,
                    "workflowName": "Release Publisher",
                    "workflowPath": ".github/workflows/release-publisher.yml",
                },
                "repository": {
                    "defaultBranch": "main",
                    "fullName": REPOSITORY,
                    "id": REPO_ID,
                },
                "schemaVersion": 2,
                "source": {
                    "archiveDigest": ARCHIVE_DIGEST,
                    "artifactDigest": SOURCE_ARTIFACT_DIGEST,
                    "artifactId": SOURCE_ARTIFACT_ID,
                    "runAttempt": SOURCE_RUN_ATTEMPT,
                    "runId": SOURCE_RUN_ID,
                    "sha": SOURCE_SHA,
                    "tag": "v1.2.3",
                    "workflowName": "Release Build",
                    "workflowPath": ".github/workflows/release-build.yml",
                },
            },
            evidence,
        )
        serialized = json.dumps(evidence, sort_keys=True)
        self.assertNotIn("timestamp", serialized.lower())
        self.assertNotIn("validatedAt", serialized)

    def test_rejects_unverified_or_malformed_facts(self) -> None:
        mutations = (
            ("repository id", lambda data: data["repository"].__setitem__("id", True)),
            ("source tag", lambda data: data["source_run"].__setitem__("head_branch", "main")),
            (
                "default head drift",
                lambda data: data["final_default_commit"].__setitem__("sha", "2" * 40),
            ),
            (
                "validator digest",
                lambda data: data["artifacts"][0].__setitem__("digest", "bad"),
            ),
            (
                "archive digest",
                lambda data: data["metadata"].__setitem__(
                    "archiveSha256", "sha256:" + "d" * 64
                ),
            ),
            (
                "ancestor relation",
                lambda data: data["comparison"].__setitem__("behind_by", 1),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                data = inputs()
                mutate(data)
                with self.assertRaises(EvidenceError):
                    build_evidence(**data)

    def test_writer_is_exclusive_and_never_clobbers_prior_evidence(self) -> None:
        evidence = build_evidence(**inputs())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proof.json"
            write_evidence(output, evidence)
            first_bytes = output.read_bytes()
            with self.assertRaises(EvidenceError):
                write_evidence(output, evidence)
            self.assertEqual(first_bytes, output.read_bytes())


if __name__ == "__main__":
    unittest.main()
