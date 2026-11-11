import logging
import tomllib
from pathlib import Path
from typing import Any

import pytest

from agent_workbench.adapters.config import (
    ENV_VARS,
    ConfigFile,
    app_data_dir,
    config_file_path,
    load_llm_config,
    read_config_file,
    tools_config_problems,
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


def test_llm_not_a_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv(ENV_VARS["backend"], "ollama")
    config_file = read_config_file(_write(tmp_path, "llm = 5\n"))
    assert config_file.parse_error is None
    assert config_file.llm_type_error == "expected table, got int"
    assert config_file.llm == {}

    with caplog.at_level(logging.WARNING, logger="agent_workbench.adapters.config"):
        assert load_llm_config(config_file) == LLMConfig()
    assert "expected table" in caplog.text


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


def test_wrong_type_overridden_by_env_var(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = _write(tmp_path, '[llm]\nbackend = "openai"\nmodel = 123\n')
    monkeypatch.setenv(ENV_VARS["model"], "from-env")
    config_file = read_config_file(path)
    assert wrong_type_keys(config_file.llm) == []

    with caplog.at_level(logging.WARNING, logger="agent_workbench.adapters.config"):
        assert load_llm_config(config_file) == LLMConfig(
            backend="openai", model="from-env"
        )
    assert caplog.text == ""


def test_wrong_type_empty_env_var_still_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, "[llm]\nmodel = 123\n")
    monkeypatch.setenv(ENV_VARS["model"], "")
    config_file = read_config_file(path)
    assert wrong_type_keys(config_file.llm) == ["model"]
    assert load_llm_config(config_file) == LLMConfig()


def test_wrong_type_keys_ignores_unknown_keys() -> None:
    assert wrong_type_keys({"backend": "openai", "extra": 1}) == []


def test_unknown_key_ignored(tmp_path: Path) -> None:
    path = _write(tmp_path, '[llm]\nmodel = "m"\nunknown = "x"\n')
    assert load_llm_config(read_config_file(path)) == LLMConfig(model="m")


def test_config_file_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert config_file_path() == tmp_path / ".agent_workbench" / "config.toml"


def test_config_file_path_is_in_app_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert app_data_dir() == tmp_path / ".agent_workbench"
    assert config_file_path() == app_data_dir() / "config.toml"


def test_tools_tables_read(tmp_path: Path) -> None:
    query = tmp_path / "queries.toml"
    path = _write(
        tmp_path,
        f"[tools.sql]\nquery_config = '{query}'\n"
        f"[tools.workspace]\nproject_dir = '{tmp_path}'\n",
    )
    config_file = read_config_file(path)
    assert config_file.tools == {
        "sql": {"query_config": str(query)},
        "workspace": {"project_dir": str(tmp_path)},
    }
    assert config_file.tools_type_error is None


def test_no_tools_table(tmp_path: Path) -> None:
    config_file = read_config_file(_write(tmp_path, '[llm]\nmodel = "m"\n'))
    assert config_file.tools == {}
    assert config_file.tools_type_error is None
    assert read_config_file(tmp_path / "missing.toml").tools == {}


def test_tools_not_a_table(tmp_path: Path) -> None:
    config_file = read_config_file(_write(tmp_path, 'tools = "x"\n'))
    assert config_file.parse_error is None
    assert config_file.tools_type_error == "expected table, got str"
    assert config_file.tools == {}


def test_broken_llm_still_reads_tools(tmp_path: Path) -> None:
    path = _write(tmp_path, f"llm = 1\n[tools.workspace]\nproject_dir = '{tmp_path}'\n")
    config_file = read_config_file(path)
    assert config_file.llm_type_error == "expected table, got int"
    assert config_file.llm == {}
    assert config_file.tools == {"workspace": {"project_dir": str(tmp_path)}}


def _config(tools: dict[str, Any], tools_type_error: str | None = None) -> ConfigFile:
    return ConfigFile(
        Path("config.toml"),
        True,
        None,
        {},
        tools=tools,
        tools_type_error=tools_type_error,
    )


@pytest.mark.parametrize(
    ("tools", "expected"),
    [
        pytest.param({}, [], id="empty"),
        pytest.param({"alpha": {}, "beta": {}}, [], id="valid-tables"),
        pytest.param(
            {"foo": {"path": "relative.toml", "count": 5, "nested": {"x": "y"}}},
            [],
            id="any-keys",
        ),
        pytest.param(
            {"alpha": {}, "beta": "x"},
            [("[tools.beta]", "error", "expected table, got str")],
            id="subtable-not-a-table",
        ),
    ],
)
def test_tools_config_problems(
    tools: dict[str, Any], expected: list[tuple[str, str, str]]
) -> None:
    assert tools_config_problems(_config(tools)) == expected


def test_tools_config_problems_type_error() -> None:
    config_file = _config({}, tools_type_error="expected table, got str")
    assert tools_config_problems(config_file) == [
        ("[tools]", "error", "expected table, got str")
    ]
