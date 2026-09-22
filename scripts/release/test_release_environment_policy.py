from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_environment import validate_release_environment


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/release/audit-release-environment.sh"


def valid_environment() -> dict:
    return {
        "id": 161088068,
        "name": "release",
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
        "protection_rules": [{"id": 1, "type": "branch_policy"}],
    }


def valid_policies() -> dict:
    return {
        "total_count": 1,
        "branch_policies": [
            {
                "id": 361472,
                "node_id": "policy-node",
                "name": "main",
            }
        ],
    }


class ReleaseEnvironmentPolicyTests(unittest.TestCase):
    def test_accepts_default_branch_only_custom_policy(self) -> None:
        self.assertEqual(
            [],
            validate_release_environment(valid_environment(), valid_policies(), "main"),
        )

    def test_accepts_explicit_branch_type_when_api_returns_it(self) -> None:
        policies = valid_policies()
        policies["branch_policies"][0]["type"] = "branch"
        self.assertEqual(
            [],
            validate_release_environment(valid_environment(), policies, "main"),
        )

    def test_rejects_unrestricted_environment(self) -> None:
        environment = valid_environment()
        environment["deployment_branch_policy"] = None
        errors = validate_release_environment(environment, valid_policies(), "main")
        self.assertTrue(any("custom deployment branch policies" in error for error in errors))

    def test_rejects_protected_branch_mode(self) -> None:
        environment = valid_environment()
        environment["deployment_branch_policy"] = {
            "protected_branches": True,
            "custom_branch_policies": False,
        }
        errors = validate_release_environment(environment, valid_policies(), "main")
        self.assertTrue(any("custom deployment branch policies" in error for error in errors))

    def test_rejects_missing_or_multiple_policies(self) -> None:
        for policies in (
            {"total_count": 0, "branch_policies": []},
            {
                "total_count": 2,
                "branch_policies": [
                    {"id": 1, "name": "main"},
                    {"id": 2, "name": "release/*"},
                ],
            },
        ):
            with self.subTest(policies=policies):
                errors = validate_release_environment(valid_environment(), policies, "main")
                self.assertTrue(any("exactly one deployment policy" in error for error in errors))

    def test_rejects_non_default_branch_policy(self) -> None:
        policies = valid_policies()
        policies["branch_policies"][0]["name"] = "release/*"
        errors = validate_release_environment(valid_environment(), policies, "main")
        self.assertTrue(any("must equal default branch 'main'" in error for error in errors))

    def test_rejects_explicit_tag_policy(self) -> None:
        policies = valid_policies()
        policies["branch_policies"][0]["type"] = "tag"
        errors = validate_release_environment(valid_environment(), policies, "main")
        self.assertTrue(any("policy type must be branch" in error for error in errors))

    def test_rejects_wrong_environment_name_or_malformed_payload(self) -> None:
        environment = valid_environment()
        environment["name"] = "production"
        self.assertTrue(validate_release_environment(environment, valid_policies(), "main"))
        self.assertTrue(validate_release_environment([], valid_policies(), "main"))
        self.assertTrue(validate_release_environment(valid_environment(), [], "main"))

    def test_cli_accepts_paginated_policy_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            environment_path = root / "environment.json"
            policies_path = root / "policies.json"
            environment_path.write_text(json.dumps(valid_environment()), encoding="utf-8")
            policies_path.write_text(json.dumps([valid_policies()]), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/release/audit-release-environment.py",
                    "--environment",
                    str(environment_path),
                    "--policies",
                    str(policies_path),
                    "--default-branch",
                    "main",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("release Environment matches", result.stdout)

    def test_live_wrapper_is_read_only(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("/environments/release", text)
        self.assertIn("/deployment-branch-policies", text)
        self.assertIn("audit-release-environment.py", text)
        for mutation in ("--method POST", "--method PUT", "--method PATCH", "--method DELETE"):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, text)


if __name__ == "__main__":
    unittest.main()
