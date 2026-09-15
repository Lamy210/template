import hashlib
import io
import json
import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "scripts/ci/resolve-trusted-main-artifact.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"


STUB = r'''#!/usr/bin/env python3
import hashlib
import io
import json
import os
import stat
import sys
import zipfile

log = os.environ["GH_STUB_LOG"]
args = " ".join(sys.argv[1:])
with open(log, "a", encoding="utf-8") as handle:
    handle.write(args + "\n")


def archive_bytes():
    buffer = io.BytesIO()
    info = zipfile.ZipInfo("profile.json", date_time=(2020, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(info, '{"profile":"test"}')
    return buffer.getvalue()

if "/actions/workflows/tests.yml/runs" in args:
    if "event=schedule" in args:
        print(json.dumps({"workflow_runs": [{
            "id": 9200,
            "run_attempt": 3,
            "head_sha": "0123456789abcdef0123456789abcdef01234567",
            "head_branch": "main",
            "event": "schedule",
            "conclusion": "success",
            "head_repository": {"full_name": "Lamy210/template"},
        }]}))
        raise SystemExit(0)
    if "event=push" in args:
        print(json.dumps({"workflow_runs": [{
            "id": 9100,
            "run_attempt": 2,
            "head_sha": "1123456789abcdef0123456789abcdef01234567",
            "head_branch": "main",
            "event": "push",
            "conclusion": "success",
            "head_repository": {"full_name": "Lamy210/template"},
        }]}))
        raise SystemExit(0)

if "/actions/runs/9200/artifacts" in args:
    payload = archive_bytes()
    print(json.dumps({"artifacts": [{
        "id": 7200,
        "name": "visual-baseline",
        "expired": False,
        "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
    }]}))
    raise SystemExit(0)

if "/actions/runs/9100/artifacts" in args:
    print(json.dumps({"artifacts": []}))
    raise SystemExit(0)

if "/actions/artifacts/7200/zip" in args:
    sys.stdout.buffer.write(archive_bytes())
    raise SystemExit(0)

print("unexpected gh invocation: " + args, file=sys.stderr)
raise SystemExit(2)
'''


class TrustedResolverEventPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "gh.log"
        gh = self.bin / "gh"
        gh.write_text(STUB, encoding="utf-8")
        gh.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def run_resolver(self, *extra):
        output = self.root / ("output-" + str(len(list(self.root.glob("output-*")))))
        env = os.environ.copy()
        env["PATH"] = str(self.bin) + os.pathsep + env["PATH"]
        env["GH_STUB_LOG"] = str(self.log)
        env["GH_TOKEN"] = "test-token"
        completed = subprocess.run(
            [
                "bash",
                str(RESOLVER),
                "--repository",
                "Lamy210/template",
                "--workflow",
                "tests.yml",
                "--artifact",
                "visual-baseline",
                "--output",
                str(output),
                *extra,
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        return completed, output

    def test_default_trust_policy_queries_push_only(self):
        completed, _ = self.run_resolver()
        self.assertEqual(completed.returncode, 4, completed.stderr)
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("event=push", log)
        self.assertNotIn("event=schedule", log)
        self.assertIn("actions/runs/9100/artifacts", log)

    def test_explicit_schedule_policy_selects_newer_scheduled_baseline(self):
        completed, output = self.run_resolver("--trusted-events", "push,schedule")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "9200")
        metadata = json.loads((output / "resolver-metadata.json").read_text())
        self.assertEqual(metadata["event"], "schedule")
        self.assertEqual(metadata["runId"], 9200)
        self.assertEqual(metadata["sourceSHA"], SHA)
        log = self.log.read_text(encoding="utf-8")
        self.assertIn("event=push", log)
        self.assertIn("event=schedule", log)
        self.assertIn("actions/runs/9200/artifacts", log)

    def test_rejects_untrusted_event_names(self):
        completed, _ = self.run_resolver("--trusted-events", "push,pull_request")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("trusted", completed.stderr.lower())

    def test_rejects_duplicate_event_names(self):
        completed, _ = self.run_resolver("--trusted-events", "push,push")
        self.assertEqual(completed.returncode, 2)


if __name__ == "__main__":
    unittest.main()
