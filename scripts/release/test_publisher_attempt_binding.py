from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.release.release_input import validate_release_input
from scripts.release.test_release_provenance import SHA
from scripts.release.test_validate_release_input import (
    PUBLISHER_SHA,
    create_app_archive,
    provenance,
    source_metadata,
)


PUBLISHER_RUN_ID = 99887766
PUBLISHER_RUN_ATTEMPT = 4


class PublisherAttemptBindingTests(unittest.TestCase):
    def test_validator_owned_metadata_records_publisher_run_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            archive = root / "unsigned-macos-app.tar.gz"
            archive_digest = create_app_archive(archive)

            errors, validated = validate_release_input(
                provenance_document=provenance(archive_digest),
                source_metadata=source_metadata(),
                archive_path=archive,
                expected_repository="example/MyApp",
                expected_workflow_path=".github/workflows/release-build.yml",
                expected_app_basename="MyApp.app",
                expected_bundle_id="com.example.MyApp",
                resolved_tag_sha=SHA,
                source_is_ancestor=True,
                publisher_sha=PUBLISHER_SHA,
                publisher_run_id=PUBLISHER_RUN_ID,
                publisher_run_attempt=PUBLISHER_RUN_ATTEMPT,
                release_scripts_root=Path(__file__).resolve().parent,
            )

        self.assertEqual([], errors)
        assert validated is not None
        self.assertEqual(PUBLISHER_RUN_ID, validated["publisherRunId"])
        self.assertEqual(PUBLISHER_RUN_ATTEMPT, validated["publisherRunAttempt"])


if __name__ == "__main__":
    unittest.main()
