# Copied from mcp_coder tests/utils/test_user_config.py at commit f88e6b55 (MarcusJellinghaus/mcp_coder#1400).
"""Tests for toml_utils module (class TestFormatTomlError of mcp_coder's test_user_config)."""

import tomllib
from pathlib import Path

import pytest

from agent_workbench.adapters.toml_utils import format_toml_error


class TestFormatTomlError:
    """Tests for format_toml_error helper function."""

    def test_format_includes_all_error_components(self, tmp_path: Path) -> None:
        """Error message includes file path, line number, content, and pointer."""
        # Setup - create file with error on line 3 to test line number extraction
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'line1 = "ok"\nline2 = "ok"\nmy_special_key = "unclosed\n',
            encoding="utf-8",
        )

        # Parse to get real TOMLDecodeError
        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Execute
            result = format_toml_error(config_file, error)

            # Verify all components are present
            assert str(config_file) in result  # file path
            assert 'File "' in result  # file path format
            assert "line 3" in result  # line number
            assert "my_special_key" in result  # line content
            assert "^" in result  # caret pointer

    def test_format_handles_file_read_error(self, tmp_path: Path) -> None:
        """Gracefully handles if file cannot be read for context."""
        # Setup - create error but then delete file
        config_file = tmp_path / "config.toml"
        config_file.write_text('key = "unclosed\n', encoding="utf-8")

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Delete file so it can't be read for context
            config_file.unlink()

            # Execute - should not raise
            result = format_toml_error(config_file, error)

            # Verify - should still have file path and error message
            assert str(config_file) in result
            assert "TOML parse error" in result

    def test_format_handles_line_out_of_range(self, tmp_path: Path) -> None:
        """Handles when error line number exceeds file lines."""
        # Setup - create error, then modify file to have fewer lines
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'line1 = "ok"\nline2 = "ok"\nline3 = "unclosed\n', encoding="utf-8"
        )

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Reduce file to 1 line so error line (3) is out of range
            config_file.write_text('only_one_line = "ok"\n', encoding="utf-8")

            # Execute - should not raise
            result = format_toml_error(config_file, error)

            # Verify - should have file path and error message
            assert str(config_file) in result
            assert "TOML parse error" in result

    def test_format_hints_at_smart_quotes(self, tmp_path: Path) -> None:
        """Curly quotes on the error line produce the smart-quote hint."""
        # Setup - value delimited by U+201C / U+201D instead of straight quotes
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[llm.langchain]\nbase_url = \u201chttps://relay/v1\u201d\n",
            encoding="utf-8",
        )

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Execute
            result = format_toml_error(config_file, error)

            # Verify - smart-quote hint present, backslash hint absent
            assert "Curly/smart quotes" in result
            assert "Use straight quotes" in result
            assert "Backslashes in paths" not in result

    def test_format_hints_at_single_smart_quotes(self, tmp_path: Path) -> None:
        """Curly single quotes (U+2018/U+2019) also trigger the hint."""
        # Setup
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "[llm.langchain]\nmodel = \u2018gpt-4o\u2019\n", encoding="utf-8"
        )

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Execute
            result = format_toml_error(config_file, error)

            # Verify
            assert "Curly/smart quotes" in result

    def test_format_backslash_hint_without_smart_quote_hint(
        self, tmp_path: Path
    ) -> None:
        """An unescaped Windows path keeps the backslash hint only."""
        # Setup
        config_file = tmp_path / "config.toml"
        config_file.write_text('path = "C:\\Users\\name"\n', encoding="utf-8")

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Execute
            result = format_toml_error(config_file, error)

            # Verify - only the backslash hint
            assert "Backslashes in paths" in result
            assert "Curly/smart quotes" not in result

    def test_format_plain_syntax_error_has_no_hints(self, tmp_path: Path) -> None:
        """A plain syntax error renders neither hint."""
        # Setup - missing '=' between key and value
        config_file = tmp_path / "config.toml"
        config_file.write_text('key "value"\n', encoding="utf-8")

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Execute
            result = format_toml_error(config_file, error)

            # Verify
            assert "Curly/smart quotes" not in result
            assert "Backslashes in paths" not in result

    def test_format_smart_quotes_unreadable_file_has_no_hint(
        self, tmp_path: Path
    ) -> None:
        """Unreadable file skips the smart-quote hint without crashing."""
        # Setup
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "base_url = \u201chttps://relay/v1\u201d\n", encoding="utf-8"
        )

        try:
            with open(config_file, "rb") as f:
                tomllib.load(f)
            pytest.fail("Expected TOMLDecodeError")
        except tomllib.TOMLDecodeError as error:
            # Delete file so the error line can't be read
            config_file.unlink()

            # Execute - should not raise
            result = format_toml_error(config_file, error)

            # Verify - no hint, but the error is still reported
            assert "TOML parse error" in result
            assert "Curly/smart quotes" not in result
