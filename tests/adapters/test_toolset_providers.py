"""Tests for toolset provider discovery and build_toolsets."""

import logging
from pathlib import Path
from typing import Any

import pytest

from agent_workbench.adapters.config import ConfigFile, read_config_file
from agent_workbench.adapters.toolset_providers import (
    ENTRY_POINT_GROUP,
    Toolsets,
    build_toolsets,
    provider_class,
    provider_packages,
    registered_providers,
)
from tests.adapters.tool_fixtures import (
    FakeProvider,
    FakeToolset,
    StubEntryPoint,
    new_provider,
    register_entry_points,
    register_providers,
    write_config_file,
)


def test_registered_providers_sorted(monkeypatch: pytest.MonkeyPatch) -> None:
    """The registered names come back sorted."""
    register_providers(monkeypatch, {"zeta": FakeProvider, "alpha": FakeProvider})

    assert registered_providers() == ["alpha", "zeta"]


def test_registered_providers_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """No entry point in the group → empty list."""
    register_providers(monkeypatch, {})

    assert not registered_providers()


def test_provider_class_loads_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The class of the entry point with the name is returned; others stay unloaded."""
    first, second = new_provider(), new_provider()
    stubs = register_providers(monkeypatch, {"first": first, "second": second})

    assert provider_class("second") is second
    assert not stubs[0].loads


def test_provider_class_unknown_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown name → ValueError listing the registered names and the install hint."""
    register_providers(monkeypatch, {"sql": FakeProvider, "workspace": FakeProvider})

    with pytest.raises(ValueError, match="'nosuch'") as exc_info:
        provider_class("nosuch")

    message = str(exc_info.value)
    assert ENTRY_POINT_GROUP in message
    assert "registered: sql, workspace" in message
    assert "install the package that provides toolset 'nosuch'" in message


def test_provider_class_unknown_name_none_registered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With nothing registered the message says so."""
    register_providers(monkeypatch, {})

    with pytest.raises(ValueError, match="registered: none"):
        provider_class("sql")


def test_provider_class_load_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """``load()`` raising → ValueError naming the provider and the cause."""
    register_entry_points(
        monkeypatch,
        [StubEntryPoint("broken", FakeProvider, ImportError("no module named x"))],
    )

    with pytest.raises(ValueError, match="'broken' failed to load: no module named x"):
        provider_class("broken")


def test_provider_packages_without_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """The top-level package comes from the entry-point value; nothing is loaded."""
    stubs = register_providers(monkeypatch, {"a": FakeProvider, "b": FakeProvider})

    assert provider_packages(["a"]) == ["tests"]
    assert all(not stub.loads for stub in stubs)


def test_provider_packages_skips_unregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Names without an entry point are skipped."""
    register_providers(monkeypatch, {"a": FakeProvider})

    assert provider_packages(["missing", "a"]) == ["tests"]


def test_build_toolsets_merges_specs_in_config_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two providers → their specs merged in config order; both toolsets kept."""
    sql, workspace = new_provider(), new_provider()
    register_providers(monkeypatch, {"sql": sql, "workspace": workspace})
    path = write_config_file(
        tmp_path,
        {
            "workspace": {"tools": ["read_file"], "async": True},
            "sql": {"tools": ["query", "list_tables"]},
        },
    )

    toolsets = build_toolsets(read_config_file(path))

    assert [spec.name for spec in toolsets.specs] == [
        "read_file",
        "query",
        "list_tables",
    ]
    assert toolsets.toolsets == (workspace.built[0], sql.built[0])


def test_build_toolsets_passes_table_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provider gets its ``[tools.<name>]`` table as its config."""
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    path = write_config_file(tmp_path, {"fake": {"group": "fake.update"}})

    toolsets = build_toolsets(read_config_file(path))

    assert [spec.group for spec in toolsets.specs] == ["fake.update"]


def test_build_toolsets_no_tools(tmp_path: Path) -> None:
    """No ``[tools]`` → no specs, nothing to close."""
    toolsets = build_toolsets(read_config_file(write_config_file(tmp_path, {})))

    assert toolsets == Toolsets(())


def test_close_closes_every_toolset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``close()`` closes both toolsets."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {"tools": ["other"]}})

    build_toolsets(read_config_file(path)).close()

    assert first.built[0].closed
    assert second.built[0].closed


def test_close_failure_logged_rest_closed(caplog: pytest.LogCaptureFixture) -> None:
    """One ``close`` raising → logged, the other toolset still closed."""
    failing = FakeToolset((), close_error="boom")
    other = FakeToolset(())

    with caplog.at_level(
        logging.WARNING, logger="agent_workbench.adapters.toolset_providers"
    ):
        Toolsets((), (failing, other)).close()

    assert failing.closed
    assert other.closed
    assert "boom" in caplog.text


def test_duplicate_tool_name_closes_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same tool name in two providers → ValueError; the built toolsets closed."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {}})

    with pytest.raises(ValueError, match="duplicate tool name 'echo'"):
        build_toolsets(read_config_file(path))

    assert first.built[0].closed
    assert second.built[0].closed


def test_build_failure_closes_built(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second provider's ``build`` raising → ValueError; the first toolset closed."""
    first, second = new_provider(), new_provider()
    register_providers(monkeypatch, {"first": first, "second": second})
    path = write_config_file(tmp_path, {"first": {}, "second": {"fail": "no file"}})

    with pytest.raises(ValueError, match=r"\[tools.second\].*no file"):
        build_toolsets(read_config_file(path))

    assert first.built[0].closed
    assert not second.built


def test_unregistered_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An unregistered ``[tools.x]`` → ValueError naming the registered providers."""
    provider = new_provider()
    register_providers(monkeypatch, {"sql": provider})
    path = write_config_file(tmp_path, {"sql": {}, "x": {}})

    with pytest.raises(ValueError, match="'x'.*registered: sql"):
        build_toolsets(read_config_file(path))

    assert provider.built[0].closed


@pytest.mark.parametrize(
    ("tools", "tools_type_error", "label"),
    [
        ({"x": 1}, None, r"\[tools.x\]"),
        ({}, "expected table, got str", r"\[tools\]"),
    ],
)
def test_shape_error_loads_no_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tools: dict[str, Any],
    tools_type_error: str | None,
    label: str,
) -> None:
    """A ``[tools]`` shape error → ValueError naming the table; no provider loaded."""
    stubs = register_providers(monkeypatch, {"x": new_provider()})
    config_file = ConfigFile(
        tmp_path / "config.toml",
        True,
        None,
        {},
        tools=tools,
        tools_type_error=tools_type_error,
    )

    with pytest.raises(ValueError, match=rf"Invalid \[tools\] config: {label}"):
        build_toolsets(config_file)

    assert not stubs[0].loads
