from __future__ import annotations

import io
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
