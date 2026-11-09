import logging
import tomllib
from pathlib import Path

import pytest

from agent_workbench.adapters.config import (
    ENV_VARS,
    config_file_path,
    load_llm_config,
    read_config_file,
    wrong_type_keys,
)
from agent_workbench.adapters.toml_utils import format_toml_error
from agent_workbench.core.config import LLMConfig


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_file_values_loaded(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "[llm]\n"
        'backend = "openai"\n'
        'model = "gpt-4o"\n'
        'api_key = "sk-test"\n'
        'base_url = "https://example.invalid/v1"\n'
        'api_version = "2024-06-01"\n',
    )
    config_file = read_config_file(path)
    assert config_file.exists
    assert config_file.parse_error is None
    assert load_llm_config(config_file) == LLMConfig(
        backend="openai",
        model="gpt-4o",
        api_key="sk-test",
        base_url="https://example.invalid/v1",
        api_version="2024-06-01",
    )


def test_env_var_overrides_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, '[llm]\nmodel = "from-file"\n')
    monkeypatch.setenv(ENV_VARS["model"], "from-env")
    assert load_llm_config(read_config_file(path)).model == "from-env"


def test_empty_env_var_counts_as_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, '[llm]\nmodel = "from-file"\n')
    monkeypatch.setenv(ENV_VARS["model"], "")
    assert load_llm_config(read_config_file(path)).model == "from-file"


def test_missing_file_all_unset(tmp_path: Path) -> None:
    config_file = read_config_file(tmp_path / "missing.toml")
    assert not config_file.exists
    assert config_file.parse_error is None
    assert config_file.llm == {}
    assert load_llm_config(config_file) == LLMConfig()


def test_missing_file_env_var_still_applies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_VARS["backend"], "ollama")
    config = load_llm_config(read_config_file(tmp_path / "missing.toml"))
    assert config == LLMConfig(backend="ollama")


def test_default_path_used_when_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, '[llm]\nmodel = "patched"\n')
    monkeypatch.setattr(
        "agent_workbench.adapters.config.config_file_path", lambda: path
    )
    assert read_config_file().path == path
    assert load_llm_config().model == "patched"


def test_invalid_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = _write(tmp_path, "[llm]\nmodel = \n")
    with pytest.raises(tomllib.TOMLDecodeError) as excinfo:
        tomllib.loads(path.read_text(encoding="utf-8"))
    monkeypatch.setenv(ENV_VARS["model"], "from-env")

    config_file = read_config_file(path)
    assert config_file.exists
    assert config_file.parse_error == format_toml_error(path, excinfo.value)
    assert config_file.llm == {}

    with caplog.at_level(logging.WARNING, logger="agent_workbench.adapters.config"):
        assert load_llm_config(config_file) == LLMConfig()
    assert "verify" in caplog.text


def test_llm_not_a_table(tmp_path: Path) -> None:
    config_file = read_config_file(_write(tmp_path, "llm = 5\n"))
    assert config_file.parse_error == "[llm] must be a table, got int"
    assert config_file.llm == {}
    assert load_llm_config(config_file) == LLMConfig()


def test_wrong_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = _write(tmp_path, '[llm]\nbackend = "openai"\nmodel = 123\n')
    monkeypatch.setenv(ENV_VARS["backend"], "ollama")
    config_file = read_config_file(path)
    assert wrong_type_keys(config_file.llm) == ["model"]

    with caplog.at_level(logging.WARNING, logger="agent_workbench.adapters.config"):
        assert load_llm_config(config_file) == LLMConfig()
    assert "model" in caplog.text
    assert "verify" in caplog.text


def test_wrong_type_keys_ignores_unknown_keys() -> None:
    assert wrong_type_keys({"backend": "openai", "extra": 1}) == []


def test_unknown_key_ignored(tmp_path: Path) -> None:
    path = _write(tmp_path, '[llm]\nmodel = "m"\nunknown = "x"\n')
    assert load_llm_config(read_config_file(path)) == LLMConfig(model="m")


def test_config_file_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config_file_path() == tmp_path / ".agent_workbench" / "config.toml"
