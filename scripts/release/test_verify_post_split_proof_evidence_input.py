from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.test_post_split_proof_evidence import (
    REPO_ROOT,
    VERIFY_SCRIPT,
    valid_evidence,
)


MAX_JSON_BYTES = 2 * 1024 * 1024


def write_valid_evidence(path: Path) -> None:
    path.write_text(json.dumps(valid_evidence()), encoding="utf-8")


def write_oversized_valid_evidence(path: Path) -> None:
    encoded = json.dumps(valid_evidence(), separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class OfflineProofEvidenceInputTests(unittest.TestCase):
    def run_verifier(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY_SCRIPT), str(path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_cli_rejects_oversized_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            evidence_path = Path(temporary_directory) / "evidence.json"
            write_oversized_valid_evidence(evidence_path)

            result = self.run_verifier(evidence_path)

        self.assertEqual(2, result.returncode)
        self.assertIn("JSON byte limit", result.stderr)

    def test_cli_rejects_symlinked_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            target = root / "evidence-target.json"
            evidence_path = root / "evidence.json"
            write_valid_evidence(target)
            evidence_path.symlink_to(target)

            result = self.run_verifier(evidence_path)

        self.assertEqual(2, result.returncode)
        self.assertIn("non-symlink", result.stderr)


if __name__ == "__main__":
    unittest.main()
