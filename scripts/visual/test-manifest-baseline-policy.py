from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/visual/emit-baseline-policy.py"


def load_script():
    spec = importlib.util.spec_from_file_location("emit_baseline_policy", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


policy = load_script()


class VisualBaselinePolicyTests(unittest.TestCase):
    def test_git_only_manifest_does_not_require_rolling_baseline(self) -> None:
        document = {
            "schemaVersion": 1,
            "profile": "fixture",
            "cases": [{"id": "git-case", "baseline": "git"}],
        }
        self.assertFalse(policy.requires_rolling_baseline(document))

    def test_any_rolling_case_requires_rolling_baseline(self) -> None:
        document = {
            "schemaVersion": 1,
            "profile": "fixture",
            "cases": [
                {"id": "git-case", "baseline": "git"},
                {"id": "rolling-case", "baseline": "rolling-main"},
            ],
        }
        self.assertTrue(policy.requires_rolling_baseline(document))

    def test_rejects_unknown_or_malformed_cases(self) -> None:
        cases = (
            {"cases": []},
            {"cases": ["bad"]},
            {"cases": [{"baseline": "external"}]},
        )
        for document in cases:
            with self.subTest(document=document):
                with self.assertRaises(policy.InputError):
                    policy.requires_rolling_baseline(document)

    def test_cli_emits_lowercase_github_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            output = root / "github-output.txt"
            manifest.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "profile": "fixture",
                        "cases": [{"id": "git-case", "baseline": "git"}],
                    }
                ),
                encoding="utf-8",
            )
            output.write_text("", encoding="utf-8")

            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--manifest",
                    str(manifest),
                    "--github-output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual(
                "requires_rolling=false\n",
                output.read_text(encoding="utf-8"),
            )

    def test_cli_rejects_duplicate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            output = root / "github-output.txt"
            manifest.write_text(
                '{"cases":[{"baseline":"git","baseline":"rolling-main"}]}',
                encoding="utf-8",
            )
            output.write_text("", encoding="utf-8")

            completed = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--manifest",
                    str(manifest),
                    "--github-output",
                    str(output),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(2, completed.returncode)
            self.assertIn("duplicate JSON key", completed.stderr)


if __name__ == "__main__":
    unittest.main()
