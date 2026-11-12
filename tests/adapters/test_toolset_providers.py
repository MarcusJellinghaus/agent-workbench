"""Tests for toolset provider discovery through the agent_workbench.toolsets group."""

import pytest

from agent_workbench.adapters.toolset_providers import (
    ENTRY_POINT_GROUP,
    provider_class,
    provider_packages,
    registered_providers,
)
from tests.adapters.tool_fixtures import (
    FakeProvider,
    StubEntryPoint,
    new_provider,
    register_entry_points,
    register_providers,
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
