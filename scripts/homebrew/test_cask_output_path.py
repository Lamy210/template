from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.homebrew.cask_output_path import validate_cask_output_path


REPO_ROOT = Path(__file__).resolve().parents[2]
RENDER_SCRIPT = REPO_ROOT / "scripts/homebrew/render-cask.sh"


class CaskOutputPathTests(unittest.TestCase):
    def test_accepts_missing_parent_below_real_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            root.mkdir()
            output = root / "Casks" / "example.rb"
            self.assertEqual([], validate_cask_output_path(root=root, output=output))

    def test_accepts_existing_regular_cask(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            casks = root / "Casks"
            casks.mkdir(parents=True)
            output = casks / "example.rb"
            output.write_text("cask \"example\"\n", encoding="utf-8")
            self.assertEqual([], validate_cask_output_path(root=root, output=output))

    def test_render_script_rejects_template_symlink_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            template = root / "template.rb"
            alternate = root / "alternate.rb"
            output = root / "rendered.rb"
            counter = root / "python-count"
            fake_bin = root / "bin"
            fake_bin.mkdir()

            template.write_text(
                'version = "{{VERSION}}"\nputs "{{DESCRIPTION}}"\n',
                encoding="utf-8",
            )
            alternate.write_text(
                'version = "{{VERSION}}"\nputs "UNTRUSTED {{DESCRIPTION}}"\n',
                encoding="utf-8",
            )

            real_python = shutil.which("python3")
            self.assertIsNotNone(real_python)
            wrapper = fake_bin / "python3"
            wrapper.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
count=0
if [[ -f "${PYTHON3_RACE_COUNTER}" ]]; then
  read -r count <"${PYTHON3_RACE_COUNTER}"
fi
count=$((count + 1))
printf '%s\\n' "${count}" >"${PYTHON3_RACE_COUNTER}"
if [[ "${count}" -eq 3 ]]; then
  rm -f "${PYTHON3_RACE_TEMPLATE}"
  ln -s "${PYTHON3_RACE_ALTERNATE}" "${PYTHON3_RACE_TEMPLATE}"
fi
exec "${REAL_PYTHON3}" "$@"
""",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "REAL_PYTHON3": real_python or "",
                    "PYTHON3_RACE_COUNTER": str(counter),
                    "PYTHON3_RACE_TEMPLATE": str(template),
                    "PYTHON3_RACE_ALTERNATE": str(alternate),
                    "CASK_TEMPLATE_ROOT": str(root),
                    "CASK_TEMPLATE": str(template),
                    "CASK_TOKEN": "example-app",
                    "VERSION": "1.2.3",
                    "SHA256": "0123456789abcdef" * 4,
                    "GITHUB_OWNER": "example",
                    "GITHUB_REPO": "example-app",
                    "DMG_BASENAME": "ExampleApp-v#{version}.dmg",
                    "APP_NAME": "ExampleApp",
                    "DESCRIPTION": "safe description",
                    "HOMEPAGE": "https://example.com",
                    "BUNDLE_ID": "com.example.ExampleApp",
                    "CASK_OUTPUT_ROOT": str(root),
                    "OUTPUT_CASK": str(output),
                }
            )

            result = subprocess.run(
                ["bash", str(RENDER_SCRIPT)],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertTrue(template.is_symlink())
            self.assertIn("without following symlinks", result.stderr)

    def test_render_script_rejects_template_parent_symlink_race(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source_root = root / "source"
            trusted_homebrew = source_root / "templates" / "homebrew"
            trusted_homebrew.mkdir(parents=True)
            template = trusted_homebrew / "Cask.rb.template"
            template.write_text(
                'version = "{{VERSION}}"\nputs "TRUSTED {{DESCRIPTION}}"\n',
                encoding="utf-8",
            )

            alternate_templates = root / "alternate-templates"
            alternate_homebrew = alternate_templates / "homebrew"
            alternate_homebrew.mkdir(parents=True)
            (alternate_homebrew / "Cask.rb.template").write_text(
                'version = "{{VERSION}}"\nputs "UNTRUSTED {{DESCRIPTION}}"\n',
                encoding="utf-8",
            )

            output = root / "rendered-parent-race.rb"
            counter = root / "parent-python-count"
            fake_bin = root / "parent-bin"
            fake_bin.mkdir()

            real_python = shutil.which("python3")
            self.assertIsNotNone(real_python)
            wrapper = fake_bin / "python3"
            wrapper.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
count=0
if [[ -f "${PYTHON3_RACE_COUNTER}" ]]; then
  read -r count <"${PYTHON3_RACE_COUNTER}"
fi
count=$((count + 1))
printf '%s\\n' "${count}" >"${PYTHON3_RACE_COUNTER}"
if [[ "${count}" -eq 3 ]]; then
  mv "${PYTHON3_RACE_PARENT}" "${PYTHON3_RACE_PARENT}.trusted"
  ln -s "${PYTHON3_RACE_ALTERNATE_PARENT}" "${PYTHON3_RACE_PARENT}"
fi
exec "${REAL_PYTHON3}" "$@"
""",
                encoding="utf-8",
            )
            wrapper.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{fake_bin}:{environment['PATH']}",
                    "REAL_PYTHON3": real_python or "",
                    "PYTHON3_RACE_COUNTER": str(counter),
                    "PYTHON3_RACE_PARENT": str(source_root / "templates"),
                    "PYTHON3_RACE_ALTERNATE_PARENT": str(alternate_templates),
                    "CASK_TEMPLATE_ROOT": str(source_root),
                    "CASK_TEMPLATE": str(template),
                    "CASK_TOKEN": "example-app",
                    "VERSION": "1.2.3",
                    "SHA256": "0123456789abcdef" * 4,
                    "GITHUB_OWNER": "example",
                    "GITHUB_REPO": "example-app",
                    "DMG_BASENAME": "ExampleApp-v#{version}.dmg",
                    "APP_NAME": "ExampleApp",
                    "DESCRIPTION": "safe description",
                    "HOMEPAGE": "https://example.com",
                    "BUNDLE_ID": "com.example.ExampleApp",
                    "CASK_OUTPUT_ROOT": str(root),
                    "OUTPUT_CASK": str(output),
                }
            )

            result = subprocess.run(
                ["bash", str(RENDER_SCRIPT)],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertFalse(output.exists())
            self.assertTrue((source_root / "templates").is_symlink())
            self.assertIn("without following symlinks", result.stderr)

    def test_rejects_symlinked_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            base = Path(temporary_directory)
            real_root = base / "real-tap"
            real_root.mkdir()
            root = base / "tap"
            root.symlink_to(real_root, target_is_directory=True)
            errors = validate_cask_output_path(root=root, output=root / "Casks" / "example.rb")
            self.assertTrue(any("root must not be a symlink" in error for error in errors))

    def test_rejects_symlinked_casks_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            root.mkdir()
            outside = Path(temporary_directory) / "outside"
            outside.mkdir()
            (root / "Casks").symlink_to(outside, target_is_directory=True)
            errors = validate_cask_output_path(root=root, output=root / "Casks" / "example.rb")
            self.assertTrue(any("must not traverse a symlink" in error for error in errors))

    def test_rejects_symlinked_existing_cask(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            casks = root / "Casks"
            casks.mkdir(parents=True)
            outside = Path(temporary_directory) / "outside.rb"
            outside.write_text("outside\n", encoding="utf-8")
            output = casks / "example.rb"
            output.symlink_to(outside)
            errors = validate_cask_output_path(root=root, output=output)
            self.assertTrue(any("must not traverse a symlink" in error for error in errors))

    def test_rejects_output_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            root.mkdir()
            output = Path(temporary_directory) / "outside.rb"
            errors = validate_cask_output_path(root=root, output=output)
            self.assertTrue(any("remain inside" in error for error in errors))

    def test_rejects_non_directory_parent_and_non_regular_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "tap"
            root.mkdir()
            parent_file = root / "Casks"
            parent_file.write_text("not a directory\n", encoding="utf-8")
            errors = validate_cask_output_path(root=root, output=parent_file / "example.rb")
            self.assertTrue(any("parent must be a directory" in error for error in errors))

            parent_file.unlink()
            parent_file.mkdir()
            target_directory = parent_file / "example.rb"
            target_directory.mkdir()
            errors = validate_cask_output_path(root=root, output=target_directory)
            self.assertTrue(any("must be a regular file" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
