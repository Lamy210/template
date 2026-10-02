from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.release.release_asset_limits import (
    MAX_GITHUB_RELEASE_ASSETS,
    MAX_RELEASE_METADATA_JSON_BYTES,
)
from scripts.release.release_download_identity import (
    MAX_RELEASE_DMG_BYTES,
    MAX_RELEASE_METADATA_BYTES,
    release_download_manifest,
    validate_release_download_identity,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "scripts/release/resolve-release-download.py"
REPOSITORY = "Example/MyApp"
REPOSITORY_ID = 123
TAG = "v1.2.3"
ASSETS = (
    "MyApp-v1.2.3.dmg",
    "MyApp-v1.2.3.dmg.sha256",
    "release-provenance.json",
)


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def asset(asset_id: int, name: str, *, repository: str = REPOSITORY) -> dict[str, object]:
    return {
        "id": asset_id,
        "name": name,
        "state": "uploaded",
        "size": 100 + asset_id,
        "digest": digest(name),
        "url": f"https://api.github.com/repos/{repository}/releases/assets/{asset_id}",
        "browser_download_url": (
            f"https://github.com/{repository}/releases/download/{TAG}/{name}"
        ),
    }


def release_document(*, repository: str = REPOSITORY) -> dict[str, object]:
    return {
        "id": 700,
        "tag_name": TAG,
        "draft": False,
        "prerelease": False,
        "immutable": True,
        "url": f"https://api.github.com/repos/{repository}/releases/700",
        "assets": [
            asset(101, ASSETS[0], repository=repository),
            asset(102, ASSETS[1], repository=repository),
            asset(103, ASSETS[2], repository=repository),
        ],
    }


class ReleaseDownloadIdentityTests(unittest.TestCase):
    def validate(
        self,
        document: object,
        *,
        repository: str = REPOSITORY,
        repository_id: int = REPOSITORY_ID,
        tag: str = TAG,
        assets: list[str] | None = None,
    ):
        return validate_release_download_identity(
            document,
            expected_repository=repository,
            expected_repository_id=repository_id,
            expected_tag=tag,
            expected_asset_names=list(assets or ASSETS),
        )

    def test_accepts_exact_release_and_emits_deterministic_manifest(self) -> None:
        errors, identity = self.validate(release_document())

        self.assertEqual([], errors)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(
            {
                "schemaVersion": 2,
                "repository": {
                    "id": REPOSITORY_ID,
                    "fullName": REPOSITORY,
                },
                "releaseId": 700,
                "tag": TAG,
                "immutable": True,
                "assets": [
                    {
                        "id": 101,
                        "name": ASSETS[0],
                        "digest": digest(ASSETS[0]),
                        "size": 201,
                    },
                    {
                        "id": 102,
                        "name": ASSETS[1],
                        "digest": digest(ASSETS[1]),
                        "size": 202,
                    },
                    {
                        "id": 103,
                        "name": ASSETS[2],
                        "digest": digest(ASSETS[2]),
                        "size": 203,
                    },
                ],
            },
            release_download_manifest(identity),
        )

    def test_requires_native_immutable_release(self) -> None:
        for immutable, expected in (
            (False, "natively immutable"),
            (None, "boolean true"),
        ):
            with self.subTest(immutable=immutable):
                document = release_document()
                document["immutable"] = immutable
                errors, identity = self.validate(document)

                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected in error for error in errors),
                    errors,
                )

    def test_rejects_release_identity_and_state_drift(self) -> None:
        cases = (
            ("id", True, "positive integer"),
            ("id", 0, "positive integer"),
            ("tag_name", "v1.2.4", "tag identity"),
            ("draft", True, "published"),
            ("prerelease", True, "stable"),
            ("immutable", None, "immutable flag"),
            (
                "url",
                "https://api.github.com/repos/Example/Other/releases/700",
                "API URL",
            ),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field, value=value):
                document = release_document()
                document[field] = value
                errors, identity = self.validate(document)
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_rejects_asset_identity_digest_and_url_drift(self) -> None:
        mutations = (
            ("id", True, "positive integer"),
            ("state", "new", "uploaded state"),
            ("size", 0, "positive size"),
            ("digest", "sha256:BAD", "SHA-256 digest"),
            (
                "url",
                "https://api.github.com/repos/Example/Other/releases/assets/101",
                "API URL",
            ),
            (
                "browser_download_url",
                "https://github.com/Example/Other/releases/download/v1.2.3/"
                + ASSETS[0],
                "browser URL",
            ),
        )
        for field, value, expected_error in mutations:
            with self.subTest(field=field, value=value):
                document = release_document()
                assets = document["assets"]
                assert isinstance(assets, list)
                first = assets[0]
                assert isinstance(first, dict)
                first[field] = value
                errors, identity = self.validate(document)
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_rejects_oversized_expected_release_assets(self) -> None:
        cases = (
            (ASSETS[0], MAX_RELEASE_DMG_BYTES + 1),
            (ASSETS[1], MAX_RELEASE_METADATA_BYTES + 1),
            (ASSETS[2], MAX_RELEASE_METADATA_BYTES + 1),
        )
        for name, oversized in cases:
            with self.subTest(name=name):
                document = release_document()
                assets = document["assets"]
                assert isinstance(assets, list)
                target = next(
                    item
                    for item in assets
                    if isinstance(item, dict) and item.get("name") == name
                )
                target["size"] = oversized

                errors, identity = self.validate(document)

                self.assertIsNone(identity)
                self.assertTrue(
                    any(
                        name in error and "exceeds size limit" in error
                        for error in errors
                    ),
                    errors,
                )

    def test_rejects_asset_count_above_github_release_limit(self) -> None:
        document = release_document()
        document["assets"] = [
            asset(
                1000 + index,
                f"extra-{index}.zip",
            )
            for index in range(MAX_GITHUB_RELEASE_ASSETS + 1)
        ]

        errors, identity = self.validate(document)

        self.assertIsNone(identity)
        self.assertEqual(1, len(errors), errors)
        self.assertIn("asset count exceeds GitHub release limit", errors[0])

    def test_requires_exact_release_asset_roles(self) -> None:
        errors, identity = self.validate(
            release_document(),
            assets=[
                ASSETS[0],
                "other.sha256",
                "release-provenance.json",
            ],
        )

        self.assertIsNone(identity)
        self.assertTrue(
            any("matching .sha256" in error for error in errors),
            errors,
        )

    def test_rejects_duplicate_ids_names_and_asset_set_drift(self) -> None:
        duplicate_id = release_document()
        duplicate_id_assets = duplicate_id["assets"]
        assert isinstance(duplicate_id_assets, list)
        assert isinstance(duplicate_id_assets[1], dict)
        duplicate_id_assets[1]["id"] = 101

        duplicate_name = release_document()
        duplicate_name_assets = duplicate_name["assets"]
        assert isinstance(duplicate_name_assets, list)
        assert isinstance(duplicate_name_assets[1], dict)
        duplicate_name_assets[1] = asset(102, ASSETS[0])

        missing = release_document()
        missing_assets = missing["assets"]
        assert isinstance(missing_assets, list)
        missing["assets"] = missing_assets[:-1]

        extra = release_document()
        extra_assets = extra["assets"]
        assert isinstance(extra_assets, list)
        extra_assets.append(asset(104, "extra.zip"))

        for label, document, expected_error in (
            ("duplicate id", duplicate_id, "duplicated"),
            ("duplicate name", duplicate_name, "duplicated"),
            ("missing", missing, "asset set"),
            ("extra", extra, "asset set"),
        ):
            with self.subTest(label=label):
                errors, identity = self.validate(document)
                self.assertIsNone(identity)
                self.assertTrue(
                    any(expected_error in error for error in errors),
                    errors,
                )

    def test_rejects_malformed_expectations(self) -> None:
        errors, identity = self.validate(
            release_document(),
            repository="../escape",
            repository_id=0,
            tag="v01.2.3",
            assets=["unsafe/name.dmg", "unsafe/name.dmg"],
        )

        self.assertIsNone(identity)
        self.assertTrue(any("owner/repo" in error for error in errors))
        self.assertTrue(any("repository id" in error for error in errors))
        self.assertTrue(any("stable SemVer" in error for error in errors))
        self.assertTrue(any("unique" in error for error in errors))
        self.assertTrue(any("unsafe" in error for error in errors))

    def test_cli_rejects_oversized_metadata_before_json_parse(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata = root / "release.json"
            output = root / "manifest.json"
            with metadata.open("wb") as handle:
                handle.truncate(MAX_RELEASE_METADATA_JSON_BYTES + 1)

            command = [
                sys.executable,
                str(CLI),
                "--metadata",
                str(metadata),
                "--repository",
                REPOSITORY,
                "--repository-id",
                str(REPOSITORY_ID),
                "--tag",
                TAG,
            ]
            for name in ASSETS:
                command.extend(["--asset", name])
            command.extend(["--output", str(output)])

            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("snapshot byte limit", result.stderr)
        self.assertFalse(output.exists())

    def test_cli_rejects_symlinked_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            real_metadata = root / "real-release.json"
            metadata = root / "release.json"
            output = root / "manifest.json"
            real_metadata.write_text(
                json.dumps(release_document()) + "\n",
                encoding="utf-8",
            )
            metadata.symlink_to(real_metadata.name)

            command = [
                sys.executable,
                str(CLI),
                "--metadata",
                str(metadata),
                "--repository",
                REPOSITORY,
                "--repository-id",
                str(REPOSITORY_ID),
                "--tag",
                TAG,
            ]
            for name in ASSETS:
                command.extend(["--asset", name])
            command.extend(["--output", str(output)])

            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(1, result.returncode)
        self.assertIn("regular non-symlink file", result.stderr)
        self.assertFalse(output.exists())

    def test_cli_writes_once_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            metadata = root / "release.json"
            output = root / "manifest.json"
            metadata.write_text(
                json.dumps(release_document()) + "\n",
                encoding="utf-8",
            )

            command = [
                sys.executable,
                str(CLI),
                "--metadata",
                str(metadata),
                "--repository",
                REPOSITORY,
                "--repository-id",
                str(REPOSITORY_ID),
                "--tag",
                TAG,
            ]
            for name in ASSETS:
                command.extend(["--asset", name])
            command.extend(["--output", str(output)])

            first = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(0, first.returncode, first.stderr)
            original = output.read_text(encoding="utf-8")
            second = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            after_second = output.read_text(encoding="utf-8")

        self.assertEqual(1, second.returncode)
        self.assertEqual(original, after_second)


if __name__ == "__main__":
    unittest.main()
