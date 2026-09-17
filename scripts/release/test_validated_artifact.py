from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts/release/validated_artifact.py"
CLI_PATH = REPO_ROOT / "scripts/release/verify-validated-artifact.py"
ARTIFACT_DIGEST = "sha256:" + "a" * 64
PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4
PUBLISHER_SHA = "c" * 40
REPOSITORY_ID = 1367784801
SOURCE_RUN_ID = 123456789
SOURCE_RUN_ATTEMPT = 2
ARTIFACT_ID = 7001


def artifact_name(publisher_attempt: int = PUBLISHER_RUN_ATTEMPT) -> str:
    return (
        f"validated-release-input-{PUBLISHER_RUN_ID}-{publisher_attempt}-"
        f"{SOURCE_RUN_ID}-{SOURCE_RUN_ATTEMPT}"
    )


def artifact_metadata(*, name: str | None = None) -> dict[str, object]:
    return {
        "id": ARTIFACT_ID,
        "name": name or artifact_name(),
        "expired": False,
        "digest": ARTIFACT_DIGEST,
        "workflow_run": {
            "id": PUBLISHER_RUN_ID,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_sha": PUBLISHER_SHA,
        },
    }


class ValidatedArtifactTests(unittest.TestCase):
    def load_module(self):
        self.assertTrue(MODULE_PATH.is_file(), f"missing validated artifact verifier: {MODULE_PATH}")
        self.assertTrue(CLI_PATH.is_file(), f"missing validated artifact verifier CLI: {CLI_PATH}")
        spec = importlib.util.spec_from_file_location("validated_artifact_under_test", MODULE_PATH)
        self.assertIsNotNone(spec)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module

    def verify(self, module, document: object, *, name: str | None = None) -> list[str]:
        return module.verify_validated_artifact(
            artifact_metadata=document,
            artifact_id=ARTIFACT_ID,
            artifact_name=name or artifact_name(),
            artifact_digest=ARTIFACT_DIGEST,
            publisher_run_id=PUBLISHER_RUN_ID,
            publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
            source_run_id=SOURCE_RUN_ID,
            source_run_attempt=SOURCE_RUN_ATTEMPT,
        )

    def test_accepts_exact_current_publisher_attempt_artifact(self) -> None:
        module = self.load_module()
        self.assertEqual([], self.verify(module, artifact_metadata()))

    def test_rejects_artifact_from_previous_publisher_attempt(self) -> None:
        module = self.load_module()
        previous_name = artifact_name(PUBLISHER_RUN_ATTEMPT - 1)
        errors = self.verify(module, artifact_metadata(name=previous_name), name=previous_name)
        self.assertTrue(any("canonical" in error or "publisher" in error for error in errors))

    def test_rejects_identity_digest_expiration_and_run_drift(self) -> None:
        module = self.load_module()
        mutations = (
            ("id", ARTIFACT_ID + 1),
            ("digest", "sha256:" + "b" * 64),
            ("expired", True),
            ("workflow_run", {"id": PUBLISHER_RUN_ID + 1}),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = artifact_metadata()
                document[key] = value
                self.assertTrue(self.verify(module, document))

    def test_binds_artifact_to_publisher_sha_and_repository_identity(self) -> None:
        module = self.load_module()
        parameters = inspect.signature(module.verify_validated_artifact).parameters
        self.assertIn("publisher_sha", parameters)
        self.assertIn("repository_id", parameters)

        common = {
            "artifact_id": ARTIFACT_ID,
            "artifact_name": artifact_name(),
            "artifact_digest": ARTIFACT_DIGEST,
            "publisher_run_id": PUBLISHER_RUN_ID,
            "publisher_run_attempt": PUBLISHER_RUN_ATTEMPT,
            "publisher_sha": PUBLISHER_SHA,
            "repository_id": REPOSITORY_ID,
            "source_run_id": SOURCE_RUN_ID,
            "source_run_attempt": SOURCE_RUN_ATTEMPT,
        }
        self.assertEqual(
            [],
            module.verify_validated_artifact(
                artifact_metadata=artifact_metadata(),
                **common,
            ),
        )

        mutations = (
            ("head_sha", "d" * 40),
            ("repository_id", REPOSITORY_ID + 1),
            ("head_repository_id", REPOSITORY_ID + 1),
        )
        for key, value in mutations:
            with self.subTest(key=key):
                document = artifact_metadata()
                assert isinstance(document["workflow_run"], dict)
                document["workflow_run"][key] = value
                errors = module.verify_validated_artifact(
                    artifact_metadata=document,
                    **common,
                )
                self.assertTrue(errors)

    def test_rejects_non_object_and_malformed_expected_values(self) -> None:
        module = self.load_module()
        self.assertTrue(self.verify(module, []))
        errors = module.verify_validated_artifact(
            artifact_metadata=artifact_metadata(),
            artifact_id=True,
            artifact_name=artifact_name(),
            artifact_digest="sha512:" + "a" * 64,
            publisher_run_id=PUBLISHER_RUN_ID,
            publisher_run_attempt=0,
            source_run_id=SOURCE_RUN_ID,
            source_run_attempt=SOURCE_RUN_ATTEMPT,
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
