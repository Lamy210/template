from __future__ import annotations

import re
import unittest

from scripts.ci.workflow_yaml_keys import (
    YAML_BLOCK_SCALAR_HEADER_RE,
    YAML_KEY_TOKEN,
    normalize_yaml_key,
    strip_yaml_inline_comment,
    workflow_job_ranges,
    yaml_key_pattern,
    yaml_mapping_child_indent,
    yaml_mapping_key_indent,
    yaml_sequence_item_end,
)


class WorkflowYamlKeyTests(unittest.TestCase):
    def test_fixed_key_pattern_accepts_plain_and_quoted_keys(self) -> None:
        pattern = re.compile(rf"^{yaml_key_pattern('uses')}:$")
        for value in ("uses:", '"uses":', "'uses':"):
            with self.subTest(value=value):
                self.assertIsNotNone(pattern.fullmatch(value))

    def test_block_scalar_header_accepts_chomping_and_indent_indicators(self) -> None:
        for header in (
            "|",
            ">",
            "|-",
            "|+",
            ">-",
            ">+",
            "|2",
            "|2-",
            "|-2",
            "|2+",
            "|+2",
            ">9",
            ">9-",
            ">+9",
        ):
            with self.subTest(header=header):
                self.assertIsNotNone(
                    YAML_BLOCK_SCALAR_HEADER_RE.fullmatch(header)
                )

    def test_block_scalar_header_rejects_invalid_indent_indicators(self) -> None:
        for header in ("|0", ">0", "|10", "|-+", "||"):
            with self.subTest(header=header):
                self.assertIsNone(
                    YAML_BLOCK_SCALAR_HEADER_RE.fullmatch(header)
                )

    def test_generic_key_token_accepts_supported_key_forms(self) -> None:
        pattern = re.compile(rf"^(?P<key>{YAML_KEY_TOKEN}):$")
        for value, expected in (
            ("contents:", "contents"),
            ('"contents":', "contents"),
            ("'contents':", "contents"),
        ):
            with self.subTest(value=value):
                match = pattern.fullmatch(value)
                self.assertIsNotNone(match)
                assert match is not None
                self.assertEqual(expected, normalize_yaml_key(match.group("key")))

    def test_inline_comment_parser_honors_yaml_quote_escapes(self) -> None:
        double_quoted = r'"echo \" # literal"'
        single_quoted = "'it''s # literal'"
        self.assertEqual(
            double_quoted,
            strip_yaml_inline_comment(double_quoted),
        )
        self.assertEqual(
            single_quoted,
            strip_yaml_inline_comment(single_quoted),
        )

    def test_inline_comment_parser_strips_only_unquoted_comment(self) -> None:
        self.assertEqual(
            "value",
            strip_yaml_inline_comment("value # comment"),
        )
        self.assertEqual(
            "",
            strip_yaml_inline_comment("# whole-line comment"),
        )

    def test_normalize_yaml_key_does_not_modify_plain_key(self) -> None:
        self.assertEqual("pull_request_target", normalize_yaml_key("pull_request_target"))

    def test_mapping_key_indent_includes_compact_sequence_marker(self) -> None:
        self.assertEqual(8, yaml_mapping_key_indent("      ", "- "))
        self.assertEqual(8, yaml_mapping_key_indent("        ", None))

    def test_sequence_item_end_stops_when_parent_scope_resumes(self) -> None:
        lines = [
            "      - uses: owner/action@sha",
            "        with:",
            "          key: value",
            "# comment does not end YAML scope",
            "  next-job:",
            "    uses: ./.github/workflows/reusable.yml",
        ]
        self.assertEqual(
            4,
            yaml_sequence_item_end(lines, start=0, item_indent=6),
        )

    def test_sequence_item_end_stops_at_next_sibling_item(self) -> None:
        lines = [
            "      - uses: owner/one@sha",
            "        with:",
            "          key: value",
            "      - uses: owner/two@sha",
        ]
        self.assertEqual(
            3,
            yaml_sequence_item_end(lines, start=0, item_indent=6),
        )

    def test_mapping_child_indent_uses_actual_yaml_indentation(self) -> None:
        lines = [
            "jobs:",
            "    test:",
            "        runs-on: ubuntu-latest",
            "        permissions:",
            "              contents: write",
        ]
        self.assertEqual(
            4,
            yaml_mapping_child_indent(lines, parent_index=0),
        )
        self.assertEqual(
            8,
            yaml_mapping_child_indent(lines, parent_index=1),
        )
        self.assertEqual(
            14,
            yaml_mapping_child_indent(lines, parent_index=3),
        )

    def test_workflow_job_ranges_accept_deeper_valid_indentation(self) -> None:
        lines = [
            "jobs:",
            "    one:",
            "        runs-on: ubuntu-latest",
            '    "two":',
            "        runs-on: ubuntu-latest",
            "permissions: {}",
        ]
        self.assertEqual(
            [("one", 1, 3), ("two", 3, 5)],
            workflow_job_ranges(lines),
        )

    def test_workflow_job_ranges_stop_at_next_top_level_key(self) -> None:
        lines = [
            "jobs:",
            "  one:",
            "    runs-on: ubuntu-latest",
            '  "two":',
            "    runs-on: ubuntu-latest",
            "permissions:",
            "  contents: read",
        ]
        self.assertEqual(
            [("one", 1, 3), ("two", 3, 5)],
            workflow_job_ranges(lines),
        )

    def test_workflow_job_ranges_ignore_top_level_comments_inside_jobs(self) -> None:
        lines = [
            "jobs:",
            "  one:",
            "    runs-on: ubuntu-latest",
            "# comment between jobs",
            "  two:",
            "    runs-on: ubuntu-latest",
            "permissions: {}",
        ]
        self.assertEqual(
            [("one", 1, 4), ("two", 4, 6)],
            workflow_job_ranges(lines),
        )

    def test_workflow_job_ranges_reach_eof_when_jobs_is_last_section(self) -> None:
        lines = [
            "'jobs':",
            "  test:",
            "    runs-on: ubuntu-latest",
        ]
        self.assertEqual(
            [("test", 1, 3)],
            workflow_job_ranges(lines),
        )

if __name__ == "__main__":
    unittest.main()
