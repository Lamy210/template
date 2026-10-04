import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts/visual/validate-baseline-provenance.py"
SOURCE_SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64
MAX_JSON_BYTES = 2 * 1024 * 1024


def load_validator():
    spec = importlib.util.spec_from_file_location("baseline_provenance", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load baseline provenance validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_oversized_json(path: Path, payload: object) -> None:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise AssertionError("fixture unexpectedly exceeds JSON limit before padding")
    path.write_bytes(encoded + b" " * (MAX_JSON_BYTES + 1 - len(encoded)))


class BaselineProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.resolver = root / "resolver-metadata.json"
        self.bundle = root / "bundle-manifest.json"
        self.resolver_payload = {
            "schemaVersion": 1,
            "repository": "Lamy210/template",
            "repositoryId": 1367784801,
            "workflow": "tests.yml",
            "workflowId": 5001,
            "branch": "main",
            "runId": 12345,
            "runAttempt": 2,
            "sourceSHA": SOURCE_SHA,
            "event": "push",
            "artifactId": 777,
            "artifactName": "visual-baseline",
            "artifactDigest": DIGEST,
            "retrievedAt": "2026-09-15T00:00:00Z",
        }
        self.bundle_payload = {
            "schemaVersion": 1,
            "sourceRepository": "Lamy210/template",
            "workflow": "tests.yml",
            "sourceRunID": "12345",
            "runAttempt": 2,
            "sourceSHA": SOURCE_SHA,
            "profileFingerprint": "sha256:" + "c" * 64,
            "previousBaselineReference": None,
            "cases": [],
        }
        self.write_payloads()

    def tearDown(self):
        self.temp.cleanup()

    def write_payloads(self):
        self.resolver.write_text(json.dumps(self.resolver_payload), encoding="utf-8")
        self.bundle.write_text(json.dumps(self.bundle_payload), encoding="utf-8")

    def validate(self, expected_events=None):
        module = load_validator()
        kwargs = {
            "resolver_metadata_path": self.resolver,
            "bundle_manifest_path": self.bundle,
            "expected_repository": "Lamy210/template",
            "expected_workflow": "tests.yml",
            "expected_artifact": "visual-baseline",
        }
        if expected_events is not None:
            kwargs["expected_events"] = expected_events
        return module.validate_provenance(**kwargs)

    def test_accepts_exact_resolver_bundle_identity(self):
        result = self.validate()
        self.assertEqual(result["repositoryId"], 1367784801)
        self.assertEqual(result["workflowId"], 5001)
        self.assertEqual(result["runId"], 12345)
        self.assertEqual(result["sourceSHA"], SOURCE_SHA)

    def test_accepts_explicitly_trusted_schedule_event(self):
        self.resolver_payload["event"] = "schedule"
        self.write_payloads()
        result = self.validate(expected_events=("push", "schedule"))
        self.assertEqual(result["event"], "schedule")

    def test_rejects_resolver_event_outside_expected_policy(self):
        self.resolver_payload["event"] = "pull_request"
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "event"):
            self.validate(expected_events=("push", "schedule"))

    def test_rejects_missing_resolver_event_when_policy_is_explicit(self):
        self.resolver_payload.pop("event")
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "event"):
            self.validate(expected_events=("push", "schedule"))

    def test_rejects_missing_or_invalid_resolver_repository_id(self):
        for repository_id in (None, 0, -1, True, "1367784801"):
            with self.subTest(repository_id=repository_id):
                if repository_id is None:
                    self.resolver_payload.pop("repositoryId")
                else:
                    self.resolver_payload["repositoryId"] = repository_id
                self.write_payloads()
                with self.assertRaisesRegex(ValueError, "repository id"):
                    self.validate()
                self.resolver_payload["repositoryId"] = 1367784801

    def test_rejects_missing_or_invalid_resolver_workflow_id(self):
        for workflow_id in (None, 0, -1, True, "5001"):
            with self.subTest(workflow_id=workflow_id):
                if workflow_id is None:
                    self.resolver_payload.pop("workflowId")
                else:
                    self.resolver_payload["workflowId"] = workflow_id
                self.write_payloads()
                with self.assertRaisesRegex(ValueError, "workflow id"):
                    self.validate()
                self.resolver_payload["workflowId"] = 5001

    def test_rejects_bundle_source_run_mismatch(self):
        self.bundle_payload["sourceRunID"] = "99999"
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "run"):
            self.validate()

    def test_rejects_bundle_repository_mismatch(self):
        self.bundle_payload["sourceRepository"] = "other/repository"
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "repository"):
            self.validate()

    def test_rejects_unexpected_resolver_workflow(self):
        self.resolver_payload["workflow"] = "other.yml"
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "workflow"):
            self.validate()

    def test_rejects_unexpected_artifact_name(self):
        self.resolver_payload["artifactName"] = "other-artifact"
        self.write_payloads()
        with self.assertRaisesRegex(ValueError, "artifact"):
            self.validate()

    def test_rejects_oversized_resolver_metadata(self):
        write_oversized_json(self.resolver, self.resolver_payload)
        with self.assertRaisesRegex(ValueError, "JSON byte limit"):
            self.validate()

    def test_rejects_oversized_bundle_manifest(self):
        write_oversized_json(self.bundle, self.bundle_payload)
        with self.assertRaisesRegex(ValueError, "JSON byte limit"):
            self.validate()

    def test_rejects_symlinked_resolver_metadata(self):
        target = self.resolver.with_name("resolver-target.json")
        self.resolver.replace(target)
        self.resolver.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            self.validate()

    def test_rejects_symlinked_bundle_manifest(self):
        target = self.bundle.with_name("bundle-target.json")
        self.bundle.replace(target)
        self.bundle.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            self.validate()

    def test_direct_cli_remains_package_safe(self):
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
