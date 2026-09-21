from __future__ import annotations

import subprocess
import sys
import unittest

from scripts.release.artifact_identity import normalize_uploaded_artifact_identity


class ArtifactIdentityTests(unittest.TestCase):
    def test_accepts_positive_decimal_id_and_canonicalizes_bare_digest(self) -> None:
        artifact_id, digest = normalize_uploaded_artifact_identity(
            "123456789",
            "a" * 64,
        )
        self.assertEqual("123456789", artifact_id)
        self.assertEqual("sha256:" + "a" * 64, digest)

    def test_accepts_already_canonical_sha256_digest(self) -> None:
        artifact_id, digest = normalize_uploaded_artifact_identity(
            "1",
            "sha256:" + "b" * 64,
        )
        self.assertEqual("1", artifact_id)
        self.assertEqual("sha256:" + "b" * 64, digest)

    def test_rejects_invalid_artifact_ids(self) -> None:
        for value in ("", "0", "01", "-1", "+1", "1.0", "abc", " 1", "1 "):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_uploaded_artifact_identity(value, "c" * 64)

    def test_rejects_invalid_digests(self) -> None:
        for value in (
            "",
            "c" * 63,
            "C" * 64,
            "sha256:" + "c" * 63,
            "SHA256:" + "c" * 64,
            "sha512:" + "c" * 64,
            "sha256:" + "C" * 64,
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_uploaded_artifact_identity("2", value)

    def test_cli_emits_github_output_shape(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/normalize-validated-artifact-identity.py",
                "--artifact-id",
                "42",
                "--artifact-digest",
                "d" * 64,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            "id=42\ndigest=sha256:" + "d" * 64 + "\n",
            result.stdout,
        )

    def test_cli_fails_closed_for_malformed_identity(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/release/normalize-validated-artifact-identity.py",
                "--artifact-id",
                "00",
                "--artifact-digest",
                "e" * 64,
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
