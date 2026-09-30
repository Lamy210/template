from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ci.current_run_artifact_identity import (
    ValidationError,
    validate_current_run_artifact,
)


CLI = ROOT / "scripts/ci/current_run_artifact_identity.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
DIGEST = "sha256:" + "a" * 64


def artifact() -> dict[str, object]:
    return {
        "id": 7001,
        "name": "macos-e2e-visual-12345-2",
        "size_in_bytes": 512,
        "expired": False,
        "digest": DIGEST,
        "workflow_run": {
            "id": 12345,
            "repository_id": 1367784801,
            "head_repository_id": 1367784801,
            "head_sha": SHA,
        },
    }


class CurrentRunArtifactIdentityTests(unittest.TestCase):
    def validate(self, metadata=None):
        return validate_current_run_artifact(
            metadata if metadata is not None else artifact(),
            expected_artifact_id=7001,
            expected_artifact_name="macos-e2e-visual-12345-2",
            expected_artifact_digest=DIGEST,
            expected_run_id=12345,
            expected_repository_id=1367784801,
            expected_head_repository_id=1367784801,
            expected_source_sha=SHA,
        )

    def test_accepts_exact_current_run_artifact(self) -> None:
        result = self.validate()
        self.assertEqual(7001, result["artifactId"])
        self.assertEqual(12345, result["runId"])
        self.assertEqual(SHA, result["sourceSHA"])

    def test_rejects_artifact_id_drift(self) -> None:
        metadata = artifact()
        metadata["id"] = 7002
        with self.assertRaisesRegex(ValidationError, "artifact id"):
            self.validate(metadata)

    def test_rejects_name_drift(self) -> None:
        metadata = artifact()
        metadata["name"] = "macos-e2e-visual-12345-1"
        with self.assertRaisesRegex(ValidationError, "artifact name"):
            self.validate(metadata)

    def test_accepts_bare_upload_artifact_digest(self) -> None:
        result = validate_current_run_artifact(
            artifact(),
            expected_artifact_id=7001,
            expected_artifact_name="macos-e2e-visual-12345-2",
            expected_artifact_digest=DIGEST.removeprefix("sha256:"),
            expected_run_id=12345,
            expected_repository_id=1367784801,
            expected_head_repository_id=1367784801,
            expected_source_sha=SHA,
        )
        self.assertEqual(DIGEST, result["artifactDigest"])

    def test_rejects_digest_drift(self) -> None:
        metadata = artifact()
        metadata["digest"] = "sha256:" + "b" * 64
        with self.assertRaisesRegex(ValidationError, "artifact digest"):
            self.validate(metadata)

    def test_rejects_expired_artifact(self) -> None:
        metadata = artifact()
        metadata["expired"] = True
        with self.assertRaisesRegex(ValidationError, "expired"):
            self.validate(metadata)

    def test_rejects_run_drift(self) -> None:
        metadata = artifact()
        metadata["workflow_run"]["id"] = 12344
        with self.assertRaisesRegex(ValidationError, "workflow run id"):
            self.validate(metadata)

    def test_rejects_repository_drift(self) -> None:
        for field in ("repository_id", "head_repository_id"):
            with self.subTest(field=field):
                metadata = artifact()
                metadata["workflow_run"][field] = 999
                with self.assertRaisesRegex(ValidationError, "repository"):
                    self.validate(metadata)

    def test_accepts_fork_head_repository_when_explicitly_expected(self) -> None:
        metadata = artifact()
        metadata["workflow_run"]["head_repository_id"] = 2468
        result = validate_current_run_artifact(
            metadata,
            expected_artifact_id=7001,
            expected_artifact_name="macos-e2e-visual-12345-2",
            expected_artifact_digest=DIGEST,
            expected_run_id=12345,
            expected_repository_id=1367784801,
            expected_head_repository_id=2468,
            expected_source_sha=SHA,
        )
        self.assertEqual(7001, result["artifactId"])

    def test_rejects_source_sha_drift(self) -> None:
        metadata = artifact()
        metadata["workflow_run"]["head_sha"] = "1" + SHA[1:]
        with self.assertRaisesRegex(ValidationError, "source SHA"):
            self.validate(metadata)

    def test_cli_accepts_exact_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metadata_path = root / "artifact.json"
            metadata_path.write_text(json.dumps(artifact()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata_path),
                    "--artifact-id",
                    "7001",
                    "--artifact-name",
                    "macos-e2e-visual-12345-2",
                    "--artifact-digest",
                    DIGEST.removeprefix("sha256:"),
                    "--run-id",
                    "12345",
                    "--repository-id",
                    "1367784801",
                    "--head-repository-id",
                    "1367784801",
                    "--source-sha",
                    SHA,
                ],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(7001, json.loads(completed.stdout)["artifactId"])


if __name__ == "__main__":
    unittest.main()
