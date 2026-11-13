"""Tests for enabled_specs, the hard-coded tool filter."""

from mcp_coder_utils.tool_spec import ToolSpec, tool_spec

from agent_workbench.services.tool_filter import enabled_specs


def _spec(name: str, group: str) -> ToolSpec:
    """Return a spec named *name* in *group* over a small function."""

    def fn(text: str = "") -> str:
        """Return the text."""
        return text

    return tool_spec(fn, group=group, read_only=True, name=name)


def test_only_enabled_groups_and_tools_remain_in_order() -> None:
    """Schema, ``validate_sql``, read and write remain; the rest is dropped."""
    specs = [
        _spec("read_tables", "sql.schema"),
        _spec("validate_sql", "sql.validation"),
        _spec("verify", "sql.validation"),
        _spec("profile_table", "sql.profiling"),
        _spec("read_file", "workspace.read"),
        _spec("save_file", "workspace.write"),
        _spec("delete_this_file", "workspace.delete"),
        _spec("list_directory", "workspace.read"),
    ]

    assert [spec.name for spec in enabled_specs(specs)] == [
        "read_tables",
        "validate_sql",
        "read_file",
        "save_file",
        "list_directory",
    ]


def test_no_specs() -> None:
    """No specs → empty tuple."""
    assert enabled_specs([]) == ()
