from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]

POSITIONAL_AUDITS = (
    REPO_ROOT / "scripts/ci/audit-live-repository-merge-settings.sh",
    REPO_ROOT / "scripts/ci/audit-live-main-ruleset.sh",
    REPO_ROOT / "scripts/ci/audit-live-main-rules.sh",
    REPO_ROOT / "scripts/ci/audit-live-release-tag-ruleset.sh",
    REPO_ROOT / "scripts/ci/audit-live-immutable-releases.sh",
    REPO_ROOT / "scripts/release/audit-release-environment.sh",
)

ENV_FALLBACK_AUDITS = (
    REPO_ROOT / "scripts/ci/audit-live-main-ruleset.sh",
    REPO_ROOT / "scripts/ci/audit-live-main-rules.sh",
    REPO_ROOT / "scripts/ci/audit-live-release-tag-ruleset.sh",
    REPO_ROOT / "scripts/release/audit-release-environment.sh",
)

UNSAFE_REPOSITORIES = (
    "../escape",
    "./repo",
    "owner/..",
    "owner/.",
)


class LiveAuditRepositoryNameTests(unittest.TestCase):
    def fake_environment(self, root: Path) -> tuple[dict[str, str], Path]:
        fake_gh = root / "gh"
        call_log = root / "gh-calls.log"
        fake_gh.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
printf 'gh called: %s\\n' "$*" >>"${GH_AUDIT_TEST_LOG:?}"
exit 91
""",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)

        environment = os.environ.copy()
        environment["PATH"] = f"{root}:{environment['PATH']}"
        environment["GH_AUDIT_TEST_LOG"] = str(call_log)
        return environment, call_log

    def test_all_live_audits_reject_dot_components_before_gh_access(self) -> None:
        for audit in POSITIONAL_AUDITS:
            for repository in UNSAFE_REPOSITORIES:
                with self.subTest(audit=audit.name, repository=repository):
                    with tempfile.TemporaryDirectory() as temporary_directory:
                        root = Path(temporary_directory)
                        environment, call_log = self.fake_environment(root)
                        result = subprocess.run(
                            ["bash", str(audit), repository],
                            cwd=REPO_ROOT,
                            env=environment,
                            text=True,
                            capture_output=True,
                            check=False,
                        )

                        self.assertEqual(2, result.returncode, result.stderr)
                        self.assertFalse(call_log.exists())

    def test_environment_fallback_rejects_unsafe_repository_before_gh_access(self) -> None:
        for audit in ENV_FALLBACK_AUDITS:
            with self.subTest(audit=audit.name):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    root = Path(temporary_directory)
                    environment, call_log = self.fake_environment(root)
                    environment["GITHUB_REPOSITORY"] = "../escape"
                    result = subprocess.run(
                        ["bash", str(audit)],
                        cwd=REPO_ROOT,
                        env=environment,
                        text=True,
                        capture_output=True,
                        check=False,
                    )

                    self.assertEqual(2, result.returncode, result.stderr)
                    self.assertFalse(call_log.exists())


if __name__ == "__main__":
    unittest.main()
