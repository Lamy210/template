from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

from scripts.ci.audit_release_tag_ruleset import validate_live_release_tag_ruleset


REPO_ROOT = Path(__file__).resolve().parents[2]
LIVE_AUDIT = REPO_ROOT / "scripts/ci/audit-live-release-tag-ruleset.sh"


def valid_live_ruleset() -> dict:
    return {
        "id": 42,
        "name": "Immutable release tags",
        "target": "tag",
        "source_type": "Repository",
        "source": "example/repo",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["refs/tags/v*"],
                "exclude": [],
            }
        },
        "rules": [
            {
                "type": "update",
                "parameters": {"update_allows_fetch_and_merge": False},
            },
            {"type": "deletion"},
        ],
        "node_id": "RRS_example",
        "created_at": "2026-09-21T00:00:00Z",
        "updated_at": "2026-09-21T00:00:00Z",
        "current_user_can_bypass": "never",
        "_links": {"self": {"href": "https://api.github.com/example"}},
    }


class LiveReleaseTagRulesetAuditTests(unittest.TestCase):
    def test_accepts_canonical_live_release_tag_ruleset(self) -> None:
        self.assertEqual(
            [],
            validate_live_release_tag_ruleset(
                valid_live_ruleset(),
                expected_repository="example/repo",
            ),
        )

    def test_rejects_wrong_repository_source(self) -> None:
        document = valid_live_ruleset()
        document["source"] = "example/other"

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("source must equal expected repository" in error for error in errors))

    def test_rejects_parent_or_non_repository_ruleset(self) -> None:
        document = valid_live_ruleset()
        document["source_type"] = "Organization"

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("source_type must equal 'Repository'" in error for error in errors))

    def test_rejects_current_user_bypass_capability_when_reported(self) -> None:
        document = valid_live_ruleset()
        document["current_user_can_bypass"] = "always"

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("current_user_can_bypass must equal 'never'" in error for error in errors))

    def test_rejects_bypass_actor_or_creation_rule(self) -> None:
        document = valid_live_ruleset()
        document["bypass_actors"] = [
            {"actor_id": 1, "actor_type": "RepositoryRole", "bypass_mode": "always"}
        ]
        document["rules"].append({"type": "creation"})

        errors = validate_live_release_tag_ruleset(
            document,
            expected_repository="example/repo",
        )

        self.assertTrue(any("bypass_actors must be empty" in error for error in errors))
        self.assertTrue(any("unexpected release tag rule types" in error for error in errors))

    def test_cli_accepts_live_ruleset_export(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            payload = Path(temporary_directory) / "release-tag-ruleset.json"
            payload.write_text(json.dumps(valid_live_ruleset()) + "\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/ci/audit_release_tag_ruleset.py",
                    str(payload),
                    "example/repo",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the immutable release-tag contract", result.stdout)


    def test_live_wrapper_reads_list_and_exact_ruleset_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            detail = valid_live_ruleset()
            summary = {
                "id": detail["id"],
                "name": detail["name"],
                "target": detail["target"],
                "source_type": detail["source_type"],
                "source": detail["source"],
                "enforcement": detail["enforcement"],
            }
            fake_gh.write_text(
                textwrap.dedent(
                    f"""\
                    #!/usr/bin/env python3
                    import json
                    import sys

                    endpoint = sys.argv[-1]
                    if "rulesets?targets=tag&includes_parents=true&per_page=100" in endpoint:
                        print(json.dumps([[{summary!r}]]))
                        raise SystemExit(0)
                    if endpoint.endswith("rulesets/42?includes_parents=true"):
                        print(json.dumps({detail!r}))
                        raise SystemExit(0)
                    print("unexpected endpoint: " + endpoint, file=sys.stderr)
                    raise SystemExit(9)
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            env["GITHUB_REPOSITORY"] = "example/template"
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches the immutable release-tag contract", result.stdout)

    def test_live_wrapper_rejects_additional_active_tag_ruleset(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import sys

                    endpoint = sys.argv[-1]
                    if "rulesets?targets=tag&includes_parents=true&per_page=100" in endpoint:
                        expected = {
                            "id": 42,
                            "name": "Immutable release tags",
                            "target": "tag",
                            "source_type": "Repository",
                            "source": "example/repo",
                            "enforcement": "active",
                        }
                        extra = {
                            "id": 99,
                            "name": "Legacy tag policy",
                            "target": "tag",
                            "source_type": "Organization",
                            "source": "example",
                            "enforcement": "active",
                        }
                        print(json.dumps([[expected, extra]]))
                        raise SystemExit(0)
                    raise SystemExit(9)
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected exactly one active tag Ruleset overall", result.stderr)

    def test_live_wrapper_rejects_duplicate_active_named_rulesets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            fake_gh = root / "gh"
            fake_gh.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import json
                    import sys

                    endpoint = sys.argv[-1]
                    if "rulesets?targets=tag&includes_parents=true&per_page=100" in endpoint:
                        ruleset = {
                            "id": 42,
                            "name": "Immutable release tags",
                            "target": "tag",
                            "enforcement": "active",
                        }
                        duplicate = dict(ruleset, id=43)
                        print(json.dumps([[ruleset, duplicate]]))
                        raise SystemExit(0)
                    raise SystemExit(9)
                    """
                ),
                encoding="utf-8",
            )
            fake_gh.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{root}:{env['PATH']}"
            result = subprocess.run(
                ["bash", str(LIVE_AUDIT), "example/repo"],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertNotEqual(0, result.returncode)
        self.assertIn("Expected exactly one active tag Ruleset", result.stderr)

    def test_live_wrapper_is_read_only_and_targets_tag_rulesets(self) -> None:
        text = LIVE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("targets=tag", text)
        self.assertIn("includes_parents=true", text)
        self.assertIn("Immutable release tags", text)
        self.assertIn("audit_release_tag_ruleset.py", text)
        for mutation in (
            "--method POST",
            "--method PUT",
            "--method PATCH",
            "--method DELETE",
        ):
            with self.subTest(mutation=mutation):
                self.assertNotIn(mutation, text)


if __name__ == "__main__":
    unittest.main()
