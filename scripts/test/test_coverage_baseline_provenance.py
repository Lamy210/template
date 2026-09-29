from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.test.coverage_baseline_provenance import (
    ValidationError,
    validate_coverage_baseline_provenance,
)


ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "scripts/test/validate-coverage-baseline-provenance.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
FINGERPRINT = "sha256:" + "a" * 64
ARTIFACT_DIGEST = "sha256:" + "b" * 64


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
            resolver_path = root / "resolver.json"
            provenance_path = root / "provenance.json"
            summary_path = root / "summary.json"
            resolver_path.write_text(json.dumps(resolver_metadata()), encoding="utf-8")
            provenance_path.write_text(json.dumps(provenance()), encoding="utf-8")
            summary_path.write_text(json.dumps(summary()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(CLI),
                    "--resolver-metadata",
                    str(resolver_path),
                    "--baseline-provenance",
                    str(provenance_path),
                    "--baseline-summary",
                    str(summary_path),
                    "--expected-repository",
                    "Lamy210/template",
                    "--expected-workflow",
                    "tests.yml",
                    "--expected-artifact",
                    "coverage-baseline",
                ],
                cwd=temporary_directory,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["runAttempt"], 2)


if __name__ == "__main__":
    unittest.main()
