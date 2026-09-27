from __future__ import annotations

import base64
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.unprivileged_release_build_workflow import (
    EXPECTED_WORKFLOW_PATH,
    WorkflowValidationError,
    decode_github_contents_document,
    validate_unprivileged_release_build_workflow,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "examples/app-release-build.yml"
CLI = REPO_ROOT / "scripts/release/validate-unprivileged-release-build-workflow.py"
BLOB_SHA = "a" * 40


def workflow_text() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


def github_document(text: str) -> dict[str, object]:
    return {
        "type": "file",
        "path": EXPECTED_WORKFLOW_PATH,
        "sha": BLOB_SHA,
        "encoding": "base64",
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
    }


class HistoricalReleaseBuildWorkflowTests(unittest.TestCase):
    def test_current_example_is_accepted(self) -> None:
        self.assertEqual([], validate_unprivileged_release_build_workflow(workflow_text()))

    def test_decodes_exact_github_contents_file(self) -> None:
        text = workflow_text()
        self.assertEqual(text, decode_github_contents_document(github_document(text)))

    def test_decodes_wrapped_github_contents_base64(self) -> None:
        text = workflow_text()
        document = github_document(text)
        content = document["content"]
        self.assertIsInstance(content, str)
        document["content"] = "\n".join(
            content[index : index + 60]
            for index in range(0, len(content), 60)
        )

        self.assertEqual(text, decode_github_contents_document(document))

    def test_rejects_malformed_github_contents_identity(self) -> None:
        mutations = (
            ("type", lambda document: document.__setitem__("type", "symlink")),
            ("path", lambda document: document.__setitem__("path", ".github/workflows/other.yml")),
            ("sha", lambda document: document.__setitem__("sha", "BAD")),
            ("encoding", lambda document: document.__setitem__("encoding", "none")),
            ("content", lambda document: document.__setitem__("content", "%%%")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                document = github_document(workflow_text())
                mutate(document)
                with self.assertRaises(WorkflowValidationError):
                    decode_github_contents_document(document)

    def test_accepts_quoted_fully_pinned_action_targets(self) -> None:
        text = workflow_text()
        text = text.replace(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
            '"actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"',
            1,
        )
        text = text.replace(
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "'actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a'",
            1,
        )

        self.assertEqual([], validate_unprivileged_release_build_workflow(text))

    def test_rejects_privilege_and_proof_contract_drift(self) -> None:
        cases = (
            (
                "workflow write permission",
                lambda text: text.replace(
                    "permissions: {}",
                    "permissions:\n  contents: write",
                    1,
                ),
                "workflow-level permissions must equal {}",
            ),
            (
                "job write permission",
                lambda text: text.replace("contents: read", "contents: write", 1),
                "must not grant write access",
            ),
            (
                "release environment",
                lambda text: text.replace(
                    "    runs-on: macos-latest",
                    "    runs-on: macos-latest\n    environment: release",
                    1,
                ),
                "must not use an Environment",
            ),
            (
                "dot secret reference",
                lambda text: text.replace(
                    "        run: |",
                    "        env:\n          TOKEN: ${{ secrets.RELEASE_TOKEN }}\n        run: |",
                    1,
                ),
                "secrets",
            ),
            (
                "bracket secret reference",
                lambda text: text.replace(
                    "        run: |",
                    "        env:\n          TOKEN: ${{ secrets['RELEASE_TOKEN'] }}\n        run: |",
                    1,
                ),
                "secrets context",
            ),
            (
                "credential-persisting checkout",
                lambda text: text.replace("persist-credentials: false", "persist-credentials: true", 1),
                "persist-credentials: false",
            ),
            (
                "mutable checkout action ref",
                lambda text: text.replace(
                    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                    "actions/checkout@v7",
                    1,
                ),
                "full lowercase commit SHA",
            ),
            (
                "quoted mutable checkout action ref",
                lambda text: text.replace(
                    "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                    '"actions/checkout@v7"',
                    1,
                ),
                "full lowercase commit SHA",
            ),
            (
                "quoted permissions key",
                lambda text: text.replace(
                    "    permissions:\n      contents: read",
                    '    "permissions":\n      contents: write',
                    1,
                ),
                "privilege-sensitive workflow keys must not be quoted",
            ),
            (
                "yaml merge key",
                lambda text: text.replace(
                    "    runs-on: macos-latest",
                    "    runs-on: macos-latest\n    <<: *privileged",
                    1,
                ),
                "must not use YAML merge keys",
            ),
            (
                "indirect mixed-case secrets context",
                lambda text: text.replace(
                    "        run: |",
                    "        env:\n          DUMP: ${{ toJSON(SeCrEtS) }}\n        run: |",
                    1,
                ),
                "secrets context",
            ),
            (
                "mutable upload action ref",
                lambda text: text.replace(
                    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
                    "actions/upload-artifact@v7",
                    1,
                ),
                "full lowercase commit SHA",
            ),
            (
                "reusable privileged workflow",
                lambda text: text.replace(
                    "    runs-on: macos-latest",
                    "    uses: ./.github/workflows/reusable-macos-release.yml",
                    1,
                ),
                "must not call a reusable workflow",
            ),
            (
                "extra workflow trigger",
                lambda text: text.replace(
                    "on:\n  push:",
                    "on:\n  workflow_dispatch:\n  push:",
                    1,
                ),
                "triggered only by push",
            ),
            (
                "artifact identity drift",
                lambda text: text.replace(
                    "unsigned-macos-release-${{ github.run_id }}-${{ github.run_attempt }}",
                    "unsigned-macos-release",
                    1,
                ),
                "missing proof contract token",
            ),
            (
                "provenance writer removed",
                lambda text: text.replace(
                    "scripts/release/write-build-provenance.py",
                    "scripts/release/other.py",
                    1,
                ),
                "missing proof contract token",
            ),
        )

        for label, mutate, expected_error in cases:
            with self.subTest(label=label):
                errors = validate_unprivileged_release_build_workflow(
                    mutate(workflow_text())
                )
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_allows_application_specific_read_only_job_without_permissions_override(self) -> None:
        text = workflow_text().replace(
            "jobs:\n  build:",
            "jobs:\n"
            "  prepare:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Prepare\n"
            "        run: echo prepare\n"
            "  build:",
            1,
        )
        self.assertEqual([], validate_unprivileged_release_build_workflow(text))

    def test_cli_accepts_valid_contents_and_rejects_privileged_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid_path = root / "valid.json"
            invalid_path = root / "invalid.json"
            valid_path.write_text(
                json.dumps(github_document(workflow_text())),
                encoding="utf-8",
            )
            invalid_text = workflow_text().replace(
                "contents: read",
                "contents: write",
                1,
            )
            invalid_path.write_text(
                json.dumps(github_document(invalid_text)),
                encoding="utf-8",
            )

            valid = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--github-content-json",
                    str(valid_path),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            invalid = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--github-content-json",
                    str(invalid_path),
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, valid.returncode, valid.stderr)
        self.assertIn("unprivileged and proof-compatible", valid.stdout)
        self.assertEqual(1, invalid.returncode)
        self.assertIn("must not grant write access", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
