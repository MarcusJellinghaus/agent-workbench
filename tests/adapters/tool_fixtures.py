"""Fake toolset provider and helpers for tests that need tools without a tool package.

Plain helpers, no fixtures: ``register_providers`` patches the entry-point lookup
of ``adapters.toolset_providers``, as mcp_coder's toolkit runner tests do.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest
from mcp_coder_utils.tool_provider import ToolsetProvider
from mcp_coder_utils.tool_spec import ToolSpec, tool_spec
from mcp_coder_utils.tool_verify import VerifyItem

from agent_workbench.adapters import toolset_providers


@dataclass
class FakeToolset:
    """Toolset of a fake provider; records whether it was closed."""

    specs: tuple[ToolSpec, ...]
    close_error: str | None = None
    closed: bool = False

    def close(self) -> None:
        """Record the call; raise ``RuntimeError`` when ``close_error`` is set.

        Raises:
            RuntimeError: When ``close_error`` is set.
        """
        self.closed = True
        if self.close_error:
            raise RuntimeError(self.close_error)


def _make_fn(name: str, is_async: bool) -> Callable[..., Any]:
    """Return a sync or async tool function that echoes its text, named *name*."""

    def echo(text: str = "") -> str:
        """Echo the text back."""
        return f"{name}: {text}"

    async def aecho(text: str = "") -> str:
        """Echo the text back."""
        return f"{name}: {text}"

    return aecho if is_async else echo


class FakeProvider(ToolsetProvider):
    """Provider whose ``config`` drives what it builds and verifies.

    Config keys: ``tools`` (tool names, default ``["echo"]``), ``group`` (default
    ``"fake.read"``), ``async`` (async tool functions), ``async_tools`` (names of the
    tools that are async, the rest sync), ``fail`` (``build`` raises
    ``ValueError``), ``close_fails`` (the toolset's ``close`` raises), ``rows``
    (``verify`` result).
    """

    built: ClassVar[list[FakeToolset]] = []
    verify_calls: ClassVar[list[bool]] = []

    def build(self) -> FakeToolset:
        """Build the toolset described by ``config``; record it in ``built``.

        Raises:
            ValueError: When ``config["fail"]`` is set.
        """
        if self.config.get("fail"):
            raise ValueError(f"fake build failed: {self.config['fail']}")
        all_async = bool(self.config.get("async", False))
        async_tools = self.config.get("async_tools", [])
        group = self.config.get("group", "fake.read")
        specs = tuple(
            tool_spec(
                _make_fn(name, all_async or name in async_tools),
                group=group,
                read_only=True,
                name=name,
            )
            for name in self.config.get("tools", ["echo"])
        )
        toolset = FakeToolset(specs, close_error=self.config.get("close_fails"))
        type(self).built.append(toolset)
        return toolset

    def verify(self, *, connect: bool = False) -> list[VerifyItem]:
        """Record *connect* and return ``config["rows"]``."""
        type(self).verify_calls.append(connect)
        return list(self.config.get("rows", []))


def new_provider() -> type[FakeProvider]:
    """Return a fresh ``FakeProvider`` subclass with its own ``built`` / ``verify_calls``."""

    class Provider(FakeProvider):
        built: ClassVar[list[FakeToolset]] = []
        verify_calls: ClassVar[list[bool]] = []

    return Provider


@dataclass(frozen=True)
class StubEntryPoint:
    """Entry point with ``name``, ``value`` and a ``load`` returning ``cls``."""

    name: str
    cls: type
    error: Exception | None = None
    loads: list[str] = field(default_factory=list, compare=False)

    @property
    def value(self) -> str:
        """``<module>:<class>`` of ``cls``, as in a real entry point."""
        return f"{self.cls.__module__}:{self.cls.__qualname__}"

    def load(self) -> type:
        """Return ``cls``, or raise ``error`` when set.

        Raises:
            Exception: ``error``, when set.
        """
        self.loads.append(self.name)
        if self.error is not None:
            raise self.error
        return self.cls


def register_entry_points(
    monkeypatch: pytest.MonkeyPatch, stubs: list[StubEntryPoint]
) -> None:
    """Make *stubs* the entry points of the ``agent_workbench.toolsets`` group."""

    def fake_entry_points(*, group: str) -> list[StubEntryPoint]:
        return list(stubs) if group == toolset_providers.ENTRY_POINT_GROUP else []

    monkeypatch.setattr(toolset_providers, "entry_points", fake_entry_points)


def register_providers(
    monkeypatch: pytest.MonkeyPatch, providers: dict[str, type]
) -> list[StubEntryPoint]:
    """Register *providers* (entry-point name → class) in place of the installed ones.

    Returns:
        The stub entry points, in the order of *providers*.
    """
    stubs = [StubEntryPoint(name, cls) for name, cls in providers.items()]
    register_entry_points(monkeypatch, stubs)
    return stubs


def _toml_value(value: Any) -> str:
    """Return *value* (str, bool, int or list of these) as a TOML value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value)


def write_config_file(tmp_path: Path, tables: dict[str, dict[str, Any]]) -> Path:
    """Write a config file with one ``[tools.<name>]`` table per entry of *tables*.

    Returns:
        The path of the written file; read it with ``read_config_file(path)``.
    """
    lines: list[str] = []
    for name, table in tables.items():
        lines.append(f"[tools.{name}]")
        lines.extend(f"{key} = {_toml_value(value)}" for key, value in table.items())
        lines.append("")
    path = tmp_path / "config.toml"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
