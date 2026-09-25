from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.homebrew.cask_output_path import validate_cask_output_path


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
