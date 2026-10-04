from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.proof_workflow_input import (
    MAX_GITHUB_CONTENTS_JSON_BYTES,
    MAX_PROOF_WORKFLOW_BYTES,
    ProofWorkflowInputError,
    decode_bounded_workflow_base64,
    load_bounded_github_contents_file,
    load_bounded_github_contents_stream,
    read_bounded_trusted_workflow,
)
from scripts.release.test_post_split_proof_evidence import valid_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_PROOF_EVIDENCE = REPO_ROOT / "scripts/release/verify-post-split-proof-evidence.py"
MAX_JSON_BYTES = 2 * 1024 * 1024


def write_oversized_valid_evidence(path: Path) -> None:
    encoded = json.dumps(valid_evidence(), separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class ProofWorkflowInputTests(unittest.TestCase):
    def test_file_loader_rejects_oversized_and_symlinked_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            oversized = root / "oversized.json"
            with oversized.open("wb") as handle:
                handle.truncate(MAX_GITHUB_CONTENTS_JSON_BYTES + 1)

            with self.assertRaisesRegex(
                ProofWorkflowInputError,
                "snapshot byte limit",
            ):
                load_bounded_github_contents_file(oversized)

            real = root / "real.json"
            real.write_text("{}\n", encoding="utf-8")
            symlink = root / "symlink.json"
            symlink.symlink_to(real.name)
            with self.assertRaisesRegex(
                ProofWorkflowInputError,
                "regular non-symlink file",
            ):
                load_bounded_github_contents_file(symlink)

    def test_stream_loader_rejects_oversized_input(self) -> None:
        stream = io.BytesIO(b" " * (MAX_GITHUB_CONTENTS_JSON_BYTES + 1))
        with self.assertRaisesRegex(
            ProofWorkflowInputError,
            "exceeds byte limit",
        ):
            load_bounded_github_contents_stream(stream)

    def test_stream_loader_accepts_bounded_json(self) -> None:
        document = {"type": "file"}
        stream = io.BytesIO(json.dumps(document).encode("utf-8"))
        self.assertEqual(
            document,
            load_bounded_github_contents_stream(stream),
        )

    def test_base64_decoder_rejects_oversized_decoded_workflow(self) -> None:
        import base64

        encoded = base64.b64encode(
            b"x" * (MAX_PROOF_WORKFLOW_BYTES + 1)
        ).decode("ascii")
        with self.assertRaisesRegex(
            ProofWorkflowInputError,
            "decoded proof workflow exceeds byte limit",
        ):
            decode_bounded_workflow_base64(encoded)

    def test_trusted_workflow_reader_rejects_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            real = root / "workflow.yml"
            real.write_text("name: proof\n", encoding="utf-8")
            symlink = root / "trusted.yml"
            symlink.symlink_to(real.name)

            with self.assertRaisesRegex(
                ProofWorkflowInputError,
                "regular non-symlink file",
            ):
                read_bounded_trusted_workflow(symlink)


class OfflineProofEvidenceInputTests(unittest.TestCase):
    def run_verifier(self, path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFY_PROOF_EVIDENCE), str(path)],
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
            target.write_text(json.dumps(valid_evidence()), encoding="utf-8")
            evidence_path.symlink_to(target)

            result = self.run_verifier(evidence_path)

        self.assertEqual(2, result.returncode)
        self.assertIn("non-symlink", result.stderr)


if __name__ == "__main__":
    unittest.main()
