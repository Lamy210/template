from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.test.coverage_baseline_provenance import (
    ValidationError,
    build_coverage_baseline_provenance,
    validate_coverage_baseline_provenance,
)


ROOT = Path(__file__).resolve().parents[2]
VALIDATE_CLI = ROOT / "scripts/test/validate-coverage-baseline-provenance.py"
BUILD_CLI = ROOT / "scripts/test/build-coverage-baseline-provenance.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
FINGERPRINT = "sha256:" + "a" * 64
ARTIFACT_DIGEST = "sha256:" + "b" * 64
MAX_JSON_BYTES = 2 * 1024 * 1024


def resolver_metadata() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "repository": "Lamy210/template",
        "repositoryId": 1367784801,
        "workflow": "tests.yml",
        "workflowId": 358957647,
        "branch": "main",
        "runId": 12345,
        "runAttempt": 2,
        "sourceSHA": SHA,
        "event": "push",
        "artifactId": 7001,
        "artifactName": "coverage-baseline",
        "artifactDigest": ARTIFACT_DIGEST,
        "retrievedAt": "2026-09-30T00:00:00Z",
    }


def provenance() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "repository": "Lamy210/template",
        "repositoryId": 1367784801,
        "workflow": "tests.yml",
        "runId": 12345,
        "runAttempt": 2,
        "sourceSHA": SHA,
        "artifactName": "coverage-baseline",
        "coverageProfileFingerprint": FINGERPRINT,
    }


def summary() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "coverageProfileFingerprint": FINGERPRINT,
        "totals": {
            "coveredLines": 8,
            "executableLines": 10,
            "lineCoverage": 0.8,
        },
        "targets": {},
    }


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class CoverageBaselineBuilderTests(unittest.TestCase):
    def test_builds_exact_attempt_bound_provenance(self) -> None:
        payload = build_coverage_baseline_provenance(
            summary(),
            repository="Lamy210/template",
            repository_id=1367784801,
            workflow="tests.yml",
            run_id=12345,
            run_attempt=2,
            source_sha=SHA,
            artifact_name="coverage-baseline",
        )

        self.assertEqual(payload, provenance())

    def test_rejects_invalid_builder_identity(self) -> None:
        with self.assertRaisesRegex(ValidationError, "run attempt"):
            build_coverage_baseline_provenance(
                summary(),
                repository="Lamy210/template",
                repository_id=1367784801,
                workflow="tests.yml",
                run_id=12345,
                run_attempt=0,
                source_sha=SHA,
                artifact_name="coverage-baseline",
            )

    def test_builder_cli_writes_canonical_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            summary_path = root / "summary.json"
            output_path = root / "provenance.json"
            summary_path.write_text(json.dumps(summary()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILD_CLI),
                    "--summary",
                    str(summary_path),
                    "--output",
                    str(output_path),
                    "--repository",
                    "Lamy210/template",
                    "--repository-id",
                    "1367784801",
                    "--workflow",
                    "tests.yml",
                    "--run-id",
                    "12345",
                    "--run-attempt",
                    "2",
                    "--source-sha",
                    SHA,
                    "--artifact-name",
                    "coverage-baseline",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(provenance(), json.loads(output_path.read_text(encoding="utf-8")))


class CoverageBaselineProvenanceTests(unittest.TestCase):
    def validate(self, resolver=None, baseline=None, coverage=None):
        return validate_coverage_baseline_provenance(
            resolver if resolver is not None else resolver_metadata(),
            baseline if baseline is not None else provenance(),
            coverage if coverage is not None else summary(),
            expected_repository="Lamy210/template",
            expected_workflow="tests.yml",
            expected_artifact="coverage-baseline",
        )

    def run_validate_cli(self, root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(VALIDATE_CLI),
                "--resolver-metadata",
                str(root / "resolver.json"),
                "--baseline-provenance",
                str(root / "provenance.json"),
                "--baseline-summary",
                str(root / "summary.json"),
                "--expected-repository",
                "Lamy210/template",
                "--expected-workflow",
                "tests.yml",
                "--expected-artifact",
                "coverage-baseline",
            ],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )

    def write_cli_inputs(self, root: Path) -> dict[str, tuple[Path, dict[str, object]]]:
        inputs = {
            "resolver metadata": (root / "resolver.json", resolver_metadata()),
            "coverage baseline provenance": (root / "provenance.json", provenance()),
            "coverage baseline summary": (root / "summary.json", summary()),
        }
        for path, payload in inputs.values():
            path.write_text(json.dumps(payload), encoding="utf-8")
        return inputs

    def test_accepts_exact_attempt_bound_provenance(self) -> None:
        result = self.validate()

        self.assertEqual(result["repositoryId"], 1367784801)
        self.assertEqual(result["workflowId"], 358957647)
        self.assertEqual(result["runId"], 12345)
        self.assertEqual(result["runAttempt"], 2)
        self.assertEqual(result["coverageProfileFingerprint"], FINGERPRINT)

    def test_rejects_attempt_drift(self) -> None:
        baseline = provenance()
        baseline["runAttempt"] = 1

        with self.assertRaisesRegex(ValidationError, "runAttempt"):
            self.validate(baseline=baseline)

    def test_rejects_repository_id_drift(self) -> None:
        baseline = provenance()
        baseline["repositoryId"] = 999

        with self.assertRaisesRegex(ValidationError, "repositoryId"):
            self.validate(baseline=baseline)

    def test_rejects_non_main_resolver_branch(self) -> None:
        resolver = resolver_metadata()
        resolver["branch"] = "release/1.x"

        with self.assertRaisesRegex(ValidationError, "branch must be main"):
            self.validate(resolver=resolver)

    def test_rejects_resolver_schema_drift(self) -> None:
        resolver = resolver_metadata()
        resolver["schemaVersion"] = 2

        with self.assertRaisesRegex(ValidationError, "schemaVersion"):
            self.validate(resolver=resolver)

    def test_rejects_non_push_resolver_event(self) -> None:
        resolver = resolver_metadata()
        resolver["event"] = "schedule"

        with self.assertRaisesRegex(ValidationError, "event must be push"):
            self.validate(resolver=resolver)

    def test_rejects_artifact_name_drift(self) -> None:
        baseline = provenance()
        baseline["artifactName"] = "other-baseline"

        with self.assertRaisesRegex(ValidationError, "artifactName"):
            self.validate(baseline=baseline)

    def test_rejects_source_sha_drift(self) -> None:
        baseline = provenance()
        baseline["sourceSHA"] = "1" + SHA[1:]

        with self.assertRaisesRegex(ValidationError, "sourceSHA"):
            self.validate(baseline=baseline)

    def test_rejects_profile_fingerprint_drift(self) -> None:
        coverage = summary()
        coverage["coverageProfileFingerprint"] = "sha256:" + "c" * 64

        with self.assertRaisesRegex(ValidationError, "fingerprint"):
            self.validate(coverage=coverage)

    def test_rejects_unknown_provenance_fields(self) -> None:
        baseline = provenance()
        baseline["unexpected"] = True

        with self.assertRaisesRegex(ValidationError, "fields mismatch"):
            self.validate(baseline=baseline)

    def test_cli_accepts_exact_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.write_cli_inputs(root)
            completed = self.run_validate_cli(root)

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["runAttempt"], 2)

    def test_cli_rejects_oversized_json_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            labels = (
                "resolver metadata",
                "coverage baseline provenance",
                "coverage baseline summary",
            )

            for index, label in enumerate(labels):
                with self.subTest(label=label):
                    case_root = root / f"case-{index}"
                    case_root.mkdir()
                    inputs = self.write_cli_inputs(case_root)
                    path, payload = inputs[label]
                    write_oversized_json(path, payload)
                    completed = self.run_validate_cli(case_root)
                    self.assertEqual(1, completed.returncode)
                    self.assertIn("JSON byte limit", completed.stderr)

    def test_cli_rejects_symlinked_json_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            labels = (
                "resolver metadata",
                "coverage baseline provenance",
                "coverage baseline summary",
            )

            for index, label in enumerate(labels):
                with self.subTest(label=label):
                    case_root = root / f"case-{index}"
                    case_root.mkdir()
                    inputs = self.write_cli_inputs(case_root)
                    path, _payload = inputs[label]
                    target = path.with_name(path.stem + "-target.json")
                    path.replace(target)
                    path.symlink_to(target)
                    completed = self.run_validate_cli(case_root)
                    self.assertEqual(1, completed.returncode)
                    self.assertIn("non-symlink", completed.stderr)


if __name__ == "__main__":
    unittest.main()
