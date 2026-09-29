from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.post_split_proof_evidence import (
    EvidenceError,
    build_evidence,
    validate_evidence_document,
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
VALIDATION_JOB_ID = 505
VALIDATOR_ARTIFACT_ID = 303
VALIDATOR_ARTIFACT_DIGEST = "sha256:" + "c" * 64
SOURCE_ARTIFACT_ID = 404
SOURCE_ARTIFACT_DIGEST = "sha256:" + "a" * 64
ARCHIVE_DIGEST = "sha256:" + "b" * 64
REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = REPO_ROOT / "scripts/release/verify-post-split-proof-evidence.py"


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
        "publisher_jobs": [
            {
                "id": VALIDATION_JOB_ID,
                "name": "Validate release input without secrets",
                "run_id": PUBLISHER_RUN_ID,
                "head_sha": PUBLISHER_SHA,
                "workflow_name": "Release Publisher",
                "head_branch": "main",
                "status": "completed",
                "conclusion": "success",
            }
        ],
        "tag_ref": {
            "ref": "refs/tags/v1.2.3",
            "object": {
                "type": "commit",
                "sha": SOURCE_SHA,
            },
        },
        "tag_objects": [],
        "source_artifacts": [
            {
                "id": SOURCE_ARTIFACT_ID,
                "name": (
                    f"unsigned-macos-release-{SOURCE_RUN_ID}-{SOURCE_RUN_ATTEMPT}"
                ),
                "expired": False,
                "digest": SOURCE_ARTIFACT_DIGEST,
            }
        ],
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


def valid_evidence() -> dict[str, object]:
    return build_evidence(**inputs())


class PostSplitProofEvidenceTests(unittest.TestCase):
    def test_builds_closed_deterministic_verified_evidence(self) -> None:
        evidence = valid_evidence()

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
                    "validationJob": {
                        "conclusion": "success",
                        "headBranch": "main",
                        "headSHA": PUBLISHER_SHA,
                        "id": VALIDATION_JOB_ID,
                        "name": "Validate release input without secrets",
                        "runAttempt": PUBLISHER_RUN_ATTEMPT,
                        "runId": PUBLISHER_RUN_ID,
                        "status": "completed",
                        "workflowName": "Release Publisher",
                    },
                    "workflowName": "Release Publisher",
                    "workflowPath": ".github/workflows/release-publisher.yml",
                },
                "repository": {
                    "defaultBranch": "main",
                    "fullName": REPOSITORY,
                    "id": REPO_ID,
                },
                "schemaVersion": 4,
                "source": {
                    "archiveDigest": ARCHIVE_DIGEST,
                    "artifactDigest": SOURCE_ARTIFACT_DIGEST,
                    "artifactId": SOURCE_ARTIFACT_ID,
                    "liveTag": {
                        "annotatedChain": [],
                        "ref": "refs/tags/v1.2.3",
                        "refTarget": {
                            "sha": SOURCE_SHA,
                            "type": "commit",
                        },
                        "resolvedSHA": SOURCE_SHA,
                    },
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

    def test_builds_annotated_live_tag_chain(self) -> None:
        data = inputs()
        first = "2" * 40
        second = "3" * 40
        data["tag_ref"] = {
            "ref": "refs/tags/v1.2.3",
            "object": {"type": "tag", "sha": first},
        }
        data["tag_objects"] = [
            {
                "sha": first,
                "tag": "v1.2.3",
                "object": {"type": "tag", "sha": second},
            },
            {
                "sha": second,
                "tag": "inner-release-tag",
                "object": {"type": "commit", "sha": SOURCE_SHA},
            },
        ]

        evidence = build_evidence(**data)

        self.assertEqual(
            {
                "annotatedChain": [
                    {
                        "sha": first,
                        "tag": "v1.2.3",
                        "target": {"sha": second, "type": "tag"},
                    },
                    {
                        "sha": second,
                        "tag": "inner-release-tag",
                        "target": {"sha": SOURCE_SHA, "type": "commit"},
                    },
                ],
                "ref": "refs/tags/v1.2.3",
                "refTarget": {"sha": first, "type": "tag"},
                "resolvedSHA": SOURCE_SHA,
            },
            evidence["source"]["liveTag"],
        )
        self.assertEqual([], validate_evidence_document(evidence))

    def test_rejects_outer_annotated_tag_name_drift(self) -> None:
        data = inputs()
        first = "2" * 40
        data["tag_ref"] = {
            "ref": "refs/tags/v1.2.3",
            "object": {"type": "tag", "sha": first},
        }
        data["tag_objects"] = [
            {
                "sha": first,
                "tag": "v9.9.9",
                "object": {"type": "commit", "sha": SOURCE_SHA},
            }
        ]

        with self.assertRaisesRegex(
            EvidenceError,
            "outer annotated release tag object name",
        ):
            build_evidence(**data)

    def test_rejects_noncanonical_repository_full_name(self) -> None:
        for repository in ("../escape", "./repo", "owner/..", "owner/."):
            with self.subTest(repository=repository):
                data = inputs()
                data["repository"]["full_name"] = repository

                with self.assertRaisesRegex(EvidenceError, "canonical owner/repo"):
                    build_evidence(**data)

    def test_rejects_unverified_or_malformed_facts(self) -> None:
        mutations = (
            ("repository id", lambda data: data["repository"].__setitem__("id", True)),
            (
                "source tag",
                lambda data: data["source_run"].__setitem__("head_branch", "main"),
            ),
            (
                "default head drift",
                lambda data: data["final_default_commit"].__setitem__(
                    "sha", "2" * 40
                ),
            ),
            (
                "source artifact id",
                lambda data: data["source_artifacts"][0].__setitem__(
                    "id", SOURCE_ARTIFACT_ID + 1
                ),
            ),
            (
                "source artifact digest",
                lambda data: data["source_artifacts"][0].__setitem__(
                    "digest", "sha256:" + "d" * 64
                ),
            ),
            (
                "publisher validation job run",
                lambda data: data["publisher_jobs"][0].__setitem__(
                    "run_id", PUBLISHER_RUN_ID + 1
                ),
            ),
            (
                "publisher validation job conclusion",
                lambda data: data["publisher_jobs"][0].__setitem__(
                    "conclusion", "failure"
                ),
            ),
            (
                "live tag moved",
                lambda data: data["tag_ref"]["object"].__setitem__(
                    "sha", "4" * 40
                ),
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

    def test_validates_closed_schema_and_internal_consistency(self) -> None:
        self.assertEqual([], validate_evidence_document(valid_evidence()))

        mutations = (
            (
                "unexpected top-level field",
                lambda document: document.__setitem__("unexpected", True),
                "unexpected fields",
            ),
            (
                "missing source field",
                lambda document: document["source"].pop("artifactDigest"),
                "source missing fields",
            ),
            (
                "schema downgrade",
                lambda document: document.__setitem__("schemaVersion", 1),
                "schemaVersion",
            ),
            (
                "source workflow drift",
                lambda document: document["source"].__setitem__(
                    "workflowPath", ".github/workflows/other.yml"
                ),
                "source.workflowPath",
            ),
            (
                "publisher workflow drift",
                lambda document: document["publisher"].__setitem__(
                    "workflowName", "Other Publisher"
                ),
                "publisher.workflowName",
            ),
            (
                "validation job attempt drift",
                lambda document: document["publisher"]["validationJob"].__setitem__(
                    "runAttempt", PUBLISHER_RUN_ATTEMPT + 1
                ),
                "publisher.validationJob.runAttempt must equal publisher.runAttempt",
            ),
            (
                "validation job SHA drift",
                lambda document: document["publisher"]["validationJob"].__setitem__(
                    "headSHA", "2" * 40
                ),
                "publisher.validationJob.headSHA must equal publisher.sha",
            ),
            (
                "validation job branch drift",
                lambda document: document["publisher"]["validationJob"].__setitem__(
                    "headBranch", "release"
                ),
                "publisher.validationJob.headBranch must equal repository.defaultBranch",
            ),
            (
                "live tag ref drift",
                lambda document: document["source"]["liveTag"].__setitem__(
                    "ref", "refs/tags/v9.9.9"
                ),
                "source.liveTag.ref must match source.tag",
            ),
            (
                "live tag resolved SHA drift",
                lambda document: document["source"]["liveTag"].__setitem__(
                    "resolvedSHA", "5" * 40
                ),
                "source.liveTag.resolvedSHA must equal source.sha",
            ),
            (
                "live annotated chain missing",
                lambda document: document["source"]["liveTag"].__setitem__(
                    "refTarget", {"sha": "6" * 40, "type": "tag"}
                ),
                "source.liveTag annotated chain must resolve to a commit",
            ),
            (
                "default-head drift",
                lambda document: document["defaultHead"].__setitem__(
                    "finalSHA", "2" * 40
                ),
                "defaultHead.finalSHA must equal publisher.sha",
            ),
            (
                "ancestor drift",
                lambda document: document["ancestor"].__setitem__(
                    "mergeBaseSHA", "3" * 40
                ),
                "ancestor.mergeBaseSHA must equal source.sha",
            ),
            (
                "version drift",
                lambda document: document["application"].__setitem__(
                    "version", "9.9.9"
                ),
                "source.tag and application.version are inconsistent",
            ),
            (
                "boolean identity",
                lambda document: document["publisher"].__setitem__("runId", True),
                "publisher.runId",
            ),
            (
                "same source/publisher sha",
                lambda document: document["publisher"].__setitem__(
                    "sha", document["source"]["sha"]
                ),
                "source.sha must differ from publisher.sha",
            ),
            (
                "same source/validator artifact id",
                lambda document: document["publisher"].__setitem__(
                    "validatorArtifactId", document["source"]["artifactId"]
                ),
                "source.artifactId must differ",
            ),
        )

        for label, mutate, expected_error in mutations:
            with self.subTest(label=label):
                document = json.loads(json.dumps(valid_evidence()))
                mutate(document)
                errors = validate_evidence_document(document)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_persisted_evidence_rejects_noncanonical_repository_name(self) -> None:
        for repository in ("../escape", "./repo", "owner/..", "owner/."):
            with self.subTest(repository=repository):
                document = valid_evidence()
                document["repository"]["fullName"] = repository

                errors = validate_evidence_document(document)

                self.assertTrue(
                    any("canonical owner/repo" in error for error in errors),
                    errors,
                )

    def test_accepts_legacy_schema_v2_evidence(self) -> None:
        document = json.loads(json.dumps(valid_evidence()))
        document["schemaVersion"] = 2
        document["publisher"].pop("validationJob")
        document["source"].pop("liveTag")

        self.assertEqual([], validate_evidence_document(document))

    def test_accepts_legacy_schema_v3_evidence(self) -> None:
        document = json.loads(json.dumps(valid_evidence()))
        document["schemaVersion"] = 3
        document["source"].pop("liveTag")

        self.assertEqual([], validate_evidence_document(document))

    def test_rejects_live_tag_in_legacy_schema_v3(self) -> None:
        document = json.loads(json.dumps(valid_evidence()))
        document["schemaVersion"] = 3

        errors = validate_evidence_document(document)

        self.assertTrue(
            any("source unexpected fields" in error for error in errors),
            errors,
        )

    def test_rejects_validation_job_in_legacy_schema_v2(self) -> None:
        document = json.loads(json.dumps(valid_evidence()))
        document["schemaVersion"] = 2
        document["source"].pop("liveTag")

        errors = validate_evidence_document(document)

        self.assertTrue(
            any("publisher unexpected fields" in error for error in errors),
            errors,
        )

    def test_writer_refuses_invalid_evidence(self) -> None:
        evidence = valid_evidence()
        evidence["source"]["workflowName"] = "Wrong Build"

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proof.json"
            with self.assertRaises(EvidenceError):
                write_evidence(output, evidence)
            self.assertFalse(output.exists())

    def test_writer_is_exclusive_and_never_clobbers_prior_evidence(self) -> None:
        evidence = valid_evidence()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "proof.json"
            write_evidence(output, evidence)
            first_bytes = output.read_bytes()
            with self.assertRaises(EvidenceError):
                write_evidence(output, evidence)
            self.assertEqual(first_bytes, output.read_bytes())

    def test_offline_verifier_cli_accepts_valid_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            path.write_text(
                json.dumps(valid_evidence(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(VERIFY_SCRIPT), str(path)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("structurally valid and internally consistent", result.stdout)

    def test_offline_verifier_cli_rejects_invalid_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            evidence = valid_evidence()
            evidence["defaultHead"]["finalSHA"] = "2" * 40
            path.write_text(json.dumps(evidence) + "\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VERIFY_SCRIPT), str(path)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("defaultHead.finalSHA must equal publisher.sha", result.stderr)

    def test_offline_verifier_cli_reports_malformed_json_separately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "proof.json"
            path.write_text("{not-json\n", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(VERIFY_SCRIPT), str(path)],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(2, result.returncode)
        self.assertIn("unable to read proof evidence", result.stderr)


if __name__ == "__main__":
    unittest.main()
