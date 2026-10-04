from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_asset_limits import MAX_VERIFIED_RELEASE_ZIP_BYTES
from scripts.release.verified_release_artifact import (
    canonical_verified_release_artifact_name,
    verify_verified_release_artifact,
)


ARTIFACT_DIGEST = "sha256:" + "a" * 64
PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4
PUBLISHER_SHA = "c" * 40
REPOSITORY_ID = 1367784801
ARTIFACT_ID = 7002
ARTIFACT_SIZE = 4096
REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/verify-verified-release-artifact.py"
MAX_JSON_BYTES = 2 * 1024 * 1024


def artifact_name(attempt: int = PUBLISHER_RUN_ATTEMPT) -> str:
    return canonical_verified_release_artifact_name(PUBLISHER_RUN_ID, attempt)


def artifact_metadata(*, name: str | None = None) -> dict[str, object]:
    return {
        "id": ARTIFACT_ID,
        "name": name or artifact_name(),
        "expired": False,
        "digest": ARTIFACT_DIGEST,
        "size_in_bytes": ARTIFACT_SIZE,
        "workflow_run": {
            "id": PUBLISHER_RUN_ID,
            "repository_id": REPOSITORY_ID,
            "head_repository_id": REPOSITORY_ID,
            "head_sha": PUBLISHER_SHA,
        },
    }


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class VerifiedReleaseArtifactTests(unittest.TestCase):
    def verify(self, document: object, *, name: str | None = None) -> list[str]:
        return verify_verified_release_artifact(
            artifact_metadata=document,
            artifact_id=ARTIFACT_ID,
            artifact_name=name or artifact_name(),
            artifact_digest=ARTIFACT_DIGEST,
            publisher_run_id=PUBLISHER_RUN_ID,
            publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
            publisher_sha=PUBLISHER_SHA,
            repository_id=REPOSITORY_ID,
        )

    def run_metadata_cli(self, metadata_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(CLI),
                "--metadata",
                str(metadata_path),
                "--artifact-id",
                str(ARTIFACT_ID),
                "--artifact-name",
                artifact_name(),
                "--artifact-digest",
                ARTIFACT_DIGEST,
                "--publisher-run-id",
                str(PUBLISHER_RUN_ID),
                "--publisher-run-attempt",
                str(PUBLISHER_RUN_ATTEMPT),
                "--publisher-sha",
                PUBLISHER_SHA,
                "--repository-id",
                str(REPOSITORY_ID),
            ],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_accepts_exact_current_publisher_attempt_artifact(self) -> None:
        self.assertEqual([], self.verify(artifact_metadata()))

    def test_cli_rejects_oversized_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata_path = root / "artifact.json"
            write_oversized_json(metadata_path, artifact_metadata())

            result = self.run_metadata_cli(metadata_path)

        self.assertEqual(1, result.returncode)
        self.assertIn("JSON byte limit", result.stderr)

    def test_cli_rejects_symlinked_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata_path = root / "artifact.json"
            target_path = root / "artifact-target.json"
            target_path.write_text(json.dumps(artifact_metadata()), encoding="utf-8")
            metadata_path.symlink_to(target_path)

            result = self.run_metadata_cli(metadata_path)

        self.assertEqual(1, result.returncode)
        self.assertIn("non-symlink", result.stderr)

    def test_rejects_previous_attempt_name(self) -> None:
        previous = artifact_name(PUBLISHER_RUN_ATTEMPT - 1)
        errors = self.verify(artifact_metadata(name=previous), name=previous)
        self.assertTrue(any("canonical" in error or "publisher" in error for error in errors))

    def test_rejects_identity_digest_expiration_and_run_drift(self) -> None:
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
                self.assertTrue(self.verify(document))

    def test_rejects_missing_invalid_or_oversized_artifact_size(self) -> None:
        for value in (
            None,
            0,
            True,
            MAX_VERIFIED_RELEASE_ZIP_BYTES + 1,
        ):
            with self.subTest(value=value):
                document = artifact_metadata()
                if value is None:
                    document.pop("size_in_bytes")
                else:
                    document["size_in_bytes"] = value
                errors = self.verify(document)
                self.assertTrue(
                    any("size" in error for error in errors),
                    errors,
                )

    def test_binds_repository_and_publisher_sha(self) -> None:
        for key, value in (
            ("repository_id", REPOSITORY_ID + 1),
            ("head_repository_id", REPOSITORY_ID + 1),
            ("head_sha", "d" * 40),
        ):
            with self.subTest(key=key):
                document = artifact_metadata()
                assert isinstance(document["workflow_run"], dict)
                document["workflow_run"][key] = value
                self.assertTrue(self.verify(document))

    def test_cli_emits_verified_size_to_new_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata_path = root / "artifact.json"
            size_output = root / "size.txt"
            metadata_path.write_text(
                json.dumps(artifact_metadata()),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--metadata",
                    str(metadata_path),
                    "--artifact-id",
                    str(ARTIFACT_ID),
                    "--artifact-name",
                    artifact_name(),
                    "--artifact-digest",
                    ARTIFACT_DIGEST,
                    "--publisher-run-id",
                    str(PUBLISHER_RUN_ID),
                    "--publisher-run-attempt",
                    str(PUBLISHER_RUN_ATTEMPT),
                    "--publisher-sha",
                    PUBLISHER_SHA,
                    "--repository-id",
                    str(REPOSITORY_ID),
                    "--size-output",
                    str(size_output),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(f"{ARTIFACT_SIZE}\n", size_output.read_text(encoding="utf-8"))
            self.assertEqual(0o600, size_output.stat().st_mode & 0o777)

    def test_cli_refuses_existing_or_symlink_size_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata_path = root / "artifact.json"
            metadata_path.write_text(
                json.dumps(artifact_metadata()),
                encoding="utf-8",
            )
            target = root / "target.txt"
            target.write_text("keep\n", encoding="utf-8")

            for mode in ("existing", "symlink"):
                with self.subTest(mode=mode):
                    size_output = root / "size.txt"
                    size_output.unlink(missing_ok=True)
                    if mode == "existing":
                        size_output.write_text("keep\n", encoding="utf-8")
                    else:
                        size_output.symlink_to(target.name)

                    result = subprocess.run(
                        [
                            sys.executable,
                            str(CLI),
                            "--metadata",
                            str(metadata_path),
                            "--artifact-id",
                            str(ARTIFACT_ID),
                            "--artifact-name",
                            artifact_name(),
                            "--artifact-digest",
                            ARTIFACT_DIGEST,
                            "--publisher-run-id",
                            str(PUBLISHER_RUN_ID),
                            "--publisher-run-attempt",
                            str(PUBLISHER_RUN_ATTEMPT),
                            "--publisher-sha",
                            PUBLISHER_SHA,
                            "--repository-id",
                            str(REPOSITORY_ID),
                            "--size-output",
                            str(size_output),
                        ],
                        cwd=REPO_ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(1, result.returncode)
                    self.assertIn("already exists", result.stderr)
                    if mode == "existing":
                        self.assertEqual("keep\n", size_output.read_text(encoding="utf-8"))
                    else:
                        self.assertTrue(size_output.is_symlink())
                        self.assertEqual("keep\n", target.read_text(encoding="utf-8"))

    def test_rejects_malformed_expected_values(self) -> None:
        errors = verify_verified_release_artifact(
            artifact_metadata=artifact_metadata(),
            artifact_id=True,
            artifact_name="",
            artifact_digest="sha512:" + "a" * 64,
            publisher_run_id=0,
            publisher_run_attempt=False,
            publisher_sha="C" * 40,
            repository_id=0,
        )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
