import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agent_workbench.adapters.config import ENV_VARS, read_config_file
from agent_workbench.adapters.langchain._product import INSTALL_HINT
from agent_workbench.services.verify import (
    collect_install_hints,
    compute_exit_code,
    run_verify,
    verify_config,
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


def test_collect_install_hints() -> None:
    rows: dict[str, Any] = {
        "a": {"ok": False, "install_hint": "pip install a"},
        "b": {"ok": True, "install_hint": "pip install b"},
        "c": {"ok": False},
        "d": ["not", "a", "dict"],
        "overall_ok": False,
    }
    assert collect_install_hints(rows) == ["pip install a"]
