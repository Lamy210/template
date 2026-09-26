from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLERS = {
    REPO_ROOT / "scripts/ci/install-gitleaks.sh": 1,
    REPO_ROOT / "scripts/ci/install-swift-quality-tools.sh": 2,
}


def curl_commands(text: str) -> list[str]:
    commands: list[str] = []
    current: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not current and not line.startswith("curl "):
            continue
        if not current:
            current.append(line)
        else:
            current.append(line)

        if line.endswith("\\"):
            current[-1] = line[:-1].rstrip()
            continue

        commands.append(" ".join(current))
        current = []

    if current:
        raise ValueError("unterminated curl command")

    return commands


class ToolInstallerRetryPolicyTests(unittest.TestCase):
    def test_pinned_tool_downloads_retry_transport_errors_with_bounded_window(self) -> None:
        for installer, expected_downloads in INSTALLERS.items():
            with self.subTest(installer=installer.name):
                text = installer.read_text(encoding="utf-8")
                commands = curl_commands(text)
                self.assertEqual(expected_downloads, len(commands), commands)
                self.assertEqual(
                    expected_downloads,
                    text.count("shasum -a 256 --check"),
                    "every retried download must remain SHA-256 verified",
                )

                for command in commands:
                    self.assertIn("--fail", command)
                    self.assertIn("--location", command)
                    self.assertIn("--retry 3", command)
                    self.assertIn("--retry-all-errors", command)
                    self.assertIn("--retry-max-time 60", command)
                    self.assertIn("--output ", command)
                    self.assertNotIn(" > ", command)
                    self.assertNotIn(" | ", command)


if __name__ == "__main__":
    unittest.main()
