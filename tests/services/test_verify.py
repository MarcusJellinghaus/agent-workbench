import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

import pytest
from mcp_coder_utils.tool_verify import VerifyItem

from agent_workbench.adapters.config import ENV_VARS, read_config_file
from agent_workbench.adapters.langchain._product import INSTALL_HINT
from agent_workbench.services.verify import (
    collect_install_hints,
    compute_exit_code,
    run_verify,
    verify_config,
    verify_tools,
)
from tests.adapters.tool_fixtures import (
    FakeProvider,
    FakeToolset,
    StubEntryPoint,
    new_provider,
    register_entry_points,
    register_providers,
)

_VENDOR_ENV_VARS = (
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_AD_TOKEN",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "ANTHROPIC_API_KEY",
    "OLLAMA_API_KEY",
    "OPENAI_API_BASE",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_ENDPOINT",
    "OLLAMA_HOST",
)

_PASSING_CONFIG = (
    '[llm]\nbackend = "openai"\nmodel = "gpt-4o-mini"\napi_key = "sk-test"\n'
)

_PROVIDER_CHECKS = "agent_workbench.adapters.langchain._provider_checks"
_MODELS = "agent_workbench.adapters.langchain._models"


@pytest.fixture(name="config_path", autouse=True)
def _config_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for var in (*ENV_VARS.values(), *_VENDOR_ENV_VARS):
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "config.toml"
    monkeypatch.setattr(
        "agent_workbench.adapters.config.config_file_path", lambda: path
    )
    return path


@pytest.fixture(name="fake_chat_model")
def _fake_chat_model() -> Iterator[MagicMock]:
    chat_model = MagicMock()
    chat_model.invoke.return_value.content = "OK"
    with patch(
        "agent_workbench.adapters.langchain._setup._create_chat_model",
        return_value=chat_model,
    ):
        yield chat_model


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _entries(config_path: Path) -> tuple[list[dict[str, str]], bool]:
    return verify_config(read_config_file(config_path))


def _llm_values(entries: list[dict[str, str]]) -> list[tuple[str, str]]:
    return [(e["status"], e["value"]) for e in entries if e["label"] == "[llm]"]


# --- CONFIG rows ------------------------------------------------------------


def test_config_file_ok(config_path: Path) -> None:
    _write(config_path, '[llm]\nbackend = "openai"\n')
    entries, has_error = _entries(config_path)
    assert not has_error
    assert entries[0] == {
        "label": "Config file",
        "status": "ok",
        "value": str(config_path),
    }
    assert _llm_values(entries) == [
        ("ok", "backend configured (config.toml)"),
        ("info", "model not configured"),
        ("info", "api_key not configured"),
        ("info", "base_url not configured"),
        ("info", "api_version not configured"),
    ]


def test_config_env_var_source(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(config_path, '[llm]\nbackend = "openai"\n')
    monkeypatch.setenv(ENV_VARS["model"], "gpt-4o")
    entries, has_error = _entries(config_path)
    assert not has_error
    assert ("ok", "model configured (env var)") in _llm_values(entries)


def test_config_env_var_and_file(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(config_path, '[llm]\nmodel = "from-file"\n')
    monkeypatch.setenv(ENV_VARS["model"], "from-env")
    entries, _ = _entries(config_path)
    assert ("ok", "model configured (env var, also in config.toml)") in _llm_values(
        entries
    )


def test_config_empty_env_var_is_unset(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(config_path, '[llm]\nbackend = "openai"\n')
    monkeypatch.setenv(ENV_VARS["model"], "")
    entries, _ = _entries(config_path)
    assert ("info", "model not configured") in _llm_values(entries)


def test_config_no_llm_section(config_path: Path) -> None:
    _write(config_path, "")
    entries, has_error = _entries(config_path)
    assert not has_error
    assert _llm_values(entries) == [("info", "not configured")]


def test_config_missing_file(config_path: Path) -> None:
    entries, has_error = _entries(config_path)
    assert not has_error
    assert entries[:3] == [
        {"label": "Config file", "status": "warning", "value": "not found"},
        {"label": "Expected path", "status": "info", "value": str(config_path)},
        {
            "label": "Hint",
            "status": "info",
            "value": "See the Configuration section of the README to create it",
        },
    ]


def test_config_invalid_toml(config_path: Path) -> None:
    _write(config_path, "[llm\n")
    entries, has_error = _entries(config_path)
    assert has_error
    assert entries[0] == {
        "label": "Config file",
        "status": "error",
        "value": "invalid TOML",
    }
    assert entries[1]["label"] == "Parse error"
    assert entries[1]["status"] == "error"
    assert len(entries) == 2


def test_config_wrong_type(config_path: Path) -> None:
    _write(config_path, "[llm]\nmodel = 42\n")
    entries, has_error = _entries(config_path)
    assert has_error
    assert ("error", "model: expected str, got int ('42')") in _llm_values(entries)


def test_config_wrong_type_overridden_by_env_var(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(config_path, "[llm]\nmodel = 42\n")
    monkeypatch.setenv(ENV_VARS["model"], "gpt-4o")
    entries, has_error = _entries(config_path)
    assert not has_error
    assert ("ok", "model configured (env var, also in config.toml)") in _llm_values(
        entries
    )


def test_config_llm_not_a_table(config_path: Path) -> None:
    _write(config_path, "llm = 5\n")
    entries, has_error = _entries(config_path)
    assert has_error
    assert entries[0] == {
        "label": "Config file",
        "status": "ok",
        "value": str(config_path),
    }
    assert _llm_values(entries) == [("error", "expected table, got int")]
    assert not [e for e in entries if e["label"] == "Parse error"]


def test_config_unknown_key(config_path: Path) -> None:
    _write(config_path, '[llm]\nmodle = "x"\n')
    entries, has_error = _entries(config_path)
    assert not has_error
    assert (
        "warning",
        "unknown key: modle — did you mean model?",
    ) in _llm_values(entries)


# --- run_verify -------------------------------------------------------------


@pytest.mark.usefixtures("fake_chat_model")
def test_happy_path(config_path: Path) -> None:
    _write(config_path, _PASSING_CONFIG)
    with patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True):
        report = run_verify()
    assert report.config_path == config_path
    assert not report.config_has_error
    assert report.backend == "openai"
    assert report.test_prompt_error is None
    assert report.provider["overall_ok"] is True
    assert "effective_config" in report.provider
    assert report.install_hints == []
    assert report.exit_code == 0


@pytest.mark.usefixtures("fake_chat_model")
def test_package_missing(config_path: Path) -> None:
    _write(config_path, _PASSING_CONFIG)
    with patch(
        f"{_PROVIDER_CHECKS}._check_package_installed",
        side_effect=lambda name: name != "langchain_openai",
    ):
        report = run_verify()
    assert report.install_hints == ["pip install langchain-openai"]
    assert report.exit_code == 1


def test_unreachable_provider(config_path: Path, fake_chat_model: MagicMock) -> None:
    _write(config_path, _PASSING_CONFIG)
    fake_chat_model.invoke.side_effect = ConnectionError("refused")
    with patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True):
        report = run_verify()
    assert report.test_prompt_error
    assert report.provider["overall_ok"] is True
    assert report.exit_code == 1


def test_runtime_import_error(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(config_path, _PASSING_CONFIG)
    monkeypatch.setitem(sys.modules, "langchain_openai", None)
    monkeypatch.delitem(
        sys.modules,
        "agent_workbench.adapters.langchain.openai_backend",
        raising=False,
    )
    report = run_verify()
    assert report.test_prompt_error is not None
    assert INSTALL_HINT in report.test_prompt_error
    assert report.exit_code == 1


@pytest.mark.usefixtures("fake_chat_model")
def test_check_models_failure_is_exit_neutral(config_path: Path) -> None:
    _write(config_path, _PASSING_CONFIG)
    with (
        patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True),
        patch(
            f"{_PROVIDER_CHECKS}._list_models_for_backend",
            return_value={"ok": False, "value": [], "error": "x"},
        ),
    ):
        report = run_verify(check_models=True)
    assert report.provider["available_models"]["ok"] is False
    assert "model_check" in report.provider
    assert report.exit_code == 0


@pytest.mark.usefixtures("fake_chat_model")
def test_ollama_without_tool_calling(config_path: Path) -> None:
    _write(config_path, '[llm]\nbackend = "ollama"\nmodel = "llama3"\n')
    with (
        patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True),
        patch(
            f"{_MODELS}._check_ollama_daemon",
            return_value={"ok": True, "value": "reachable"},
        ),
        patch(
            f"{_MODELS}.check_ollama_tool_capability",
            return_value={"ok": False, "value": "no tool calling"},
        ),
    ):
        report = run_verify()
    assert report.test_prompt_error is None
    assert report.provider["ollama_daemon"]["ok"] is True
    assert report.provider["ollama_tools_capability"]["ok"] is False
    assert report.exit_code == 1


@pytest.mark.usefixtures("fake_chat_model")
def test_config_error_alone_exits_1(config_path: Path) -> None:
    # A real config error also empties the loaded config; isolate the CONFIG cause.
    _write(config_path, _PASSING_CONFIG)
    error_row = {"label": "[llm]", "status": "error", "value": "x"}
    with (
        patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True),
        patch(
            "agent_workbench.services.verify.verify_config",
            return_value=([error_row], True),
        ),
    ):
        report = run_verify()
    assert report.config_has_error
    assert report.config_entries == [error_row]
    assert report.provider["overall_ok"] is True
    assert report.test_prompt_error is None
    assert report.exit_code == 1


# --- TOOLS rows -------------------------------------------------------------

_ITEMS = (
    VerifyItem("config.path", "ok", "found"),
    VerifyItem("config.extra", "warning", "unknown key", hint="remove it"),
    VerifyItem("config.query_config", "error", "relative path not allowed", "use ~"),
)


def _provider(
    items: tuple[VerifyItem, ...] = (), error: Exception | None = None
) -> type[FakeProvider]:
    """Return a fake provider whose ``verify`` returns *items* or raises *error*."""

    class Provider(FakeProvider):
        built: ClassVar[list[FakeToolset]] = []
        verify_calls: ClassVar[list[bool]] = []

        def verify(self, *, connect: bool = False) -> list[VerifyItem]:
            super().verify(connect=connect)
            if error is not None:
                raise error
            return list(items)

    return Provider


def _tools(config_path: Path, *, connect: bool = False) -> list[dict[str, str]]:
    rows, has_error = verify_tools(read_config_file(config_path), connect=connect)
    assert has_error == any(row["status"] == "error" for row in rows)
    return rows


def test_tools_not_configured_loads_no_provider(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = StubEntryPoint("fake", new_provider())
    register_entry_points(monkeypatch, [stub])
    _write(config_path, _PASSING_CONFIG)
    rows, has_error = verify_tools(read_config_file(config_path), connect=True)
    assert rows == [{"label": "[tools]", "status": "info", "value": "not configured"}]
    assert not has_error
    assert not stub.loads


def test_tools_invalid_toml_not_checked(config_path: Path) -> None:
    _write(config_path, "[tools\n")
    rows, has_error = verify_tools(read_config_file(config_path), connect=True)
    assert rows == [
        {
            "label": "[tools]",
            "status": "info",
            "value": "not checked – invalid config file",
        }
    ]
    assert not has_error


def test_tools_provider_rows(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": _provider(_ITEMS)})
    _write(config_path, "[tools.fake]\n")
    assert _tools(config_path) == [
        {"label": "[tools.fake]", "status": "ok", "value": "config.path: found"},
        {
            "label": "[tools.fake]",
            "status": "warning",
            "value": "config.extra: unknown key – remove it",
        },
        {
            "label": "[tools.fake]",
            "status": "error",
            "value": "config.query_config: relative path not allowed – use ~",
        },
    ]


def test_tools_unregistered_provider(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": new_provider()})
    _write(config_path, "[tools.x]\n")
    (row,) = _tools(config_path)
    assert row["label"] == "[tools.x]"
    assert row["status"] == "error"
    assert "registered: fake" in row["value"]


def test_tools_provider_verify_raising(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": _provider(error=RuntimeError("boom"))})
    _write(config_path, "[tools.fake]\n")
    assert _tools(config_path) == [
        {
            "label": "[tools.fake]",
            "status": "error",
            "value": "verify failed: RuntimeError: boom",
        }
    ]


def test_tools_subtable_not_a_table(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = StubEntryPoint("fake", new_provider())
    register_entry_points(monkeypatch, [stub])
    _write(config_path, "[tools]\nfake = 5\n")
    assert _tools(config_path) == [
        {"label": "[tools.fake]", "status": "error", "value": "expected table, got int"}
    ]
    assert not stub.loads


def test_tools_not_a_table(config_path: Path) -> None:
    _write(config_path, 'tools = "x"\n')
    assert _tools(config_path) == [
        {"label": "[tools]", "status": "error", "value": "expected table, got str"}
    ]


@pytest.mark.usefixtures("fake_chat_model")
def test_run_verify_tools_error_exits_1(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": _provider(_ITEMS)})
    _write(config_path, _PASSING_CONFIG + "\n[tools.fake]\n")
    with patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True):
        report = run_verify()
    assert [row["status"] for row in report.tools_entries] == ["ok", "warning", "error"]
    assert report.tools_has_error
    assert not report.config_has_error
    assert report.provider["overall_ok"] is True
    assert report.test_prompt_error is None
    assert report.exit_code == 1


@pytest.mark.usefixtures("fake_chat_model")
@pytest.mark.parametrize(
    ("kwargs", "expected"), [({}, True), ({"connect_tools": False}, False)]
)
def test_run_verify_passes_connect(
    config_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, bool],
    expected: bool,
) -> None:
    provider = new_provider()
    register_providers(monkeypatch, {"fake": provider})
    _write(config_path, _PASSING_CONFIG + "\n[tools.fake]\n")
    with patch(f"{_PROVIDER_CHECKS}._check_package_installed", return_value=True):
        report = run_verify(**kwargs)
    assert provider.verify_calls == [expected]
    assert report.tools_entries == []
    assert not report.tools_has_error
    assert report.exit_code == 0


@pytest.mark.usefixtures("fake_chat_model")
def test_run_verify_tools_rows_with_broken_llm(
    config_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_providers(monkeypatch, {"fake": _provider(_ITEMS[:1])})
    _write(config_path, "[llm]\nmodel = 42\n\n[tools.fake]\n")
    report = run_verify()
    assert report.config_has_error
    assert report.tools_entries == [
        {"label": "[tools.fake]", "status": "ok", "value": "config.path: found"}
    ]
    assert not report.tools_has_error
    assert report.exit_code == 1


# --- helpers ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("config_has_error", "overall_ok", "test_prompt_ok", "expected"),
    [
        (False, True, True, 0),
        (True, True, True, 1),
        (False, False, True, 1),
        (False, True, False, 1),
        (True, False, False, 1),
    ],
)
def test_compute_exit_code(
    config_has_error: bool, overall_ok: bool, test_prompt_ok: bool, expected: int
) -> None:
    assert compute_exit_code(config_has_error, overall_ok, test_prompt_ok) == expected


def test_compute_exit_code_tools_error() -> None:
    assert compute_exit_code(False, True, True, tools_has_error=True) == 1


def test_collect_install_hints() -> None:
    rows: dict[str, Any] = {
        "a": {"ok": False, "install_hint": "pip install a"},
        "b": {"ok": True, "install_hint": "pip install b"},
        "c": {"ok": False},
        "d": ["not", "a", "dict"],
        "overall_ok": False,
    }
    assert collect_install_hints(rows) == ["pip install a"]
