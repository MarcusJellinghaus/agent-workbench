import ast
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import agent_workbench
from agent_workbench.adapters.langchain._errors_404 import _format_404_hint
from agent_workbench.adapters.langchain._exceptions import LLMAuthError
from agent_workbench.core.config import LLMConfig
from agent_workbench.interfaces.cli import main
from agent_workbench.services.verify import VerifyReport

_CONFIG = LLMConfig(backend="openai", model="gpt-4o-mini", api_key="sk-test")
_CREATE = "agent_workbench.adapters.langchain._setup._create_chat_model"
_LOAD = "agent_workbench.adapters.config.load_llm_config"


@pytest.fixture(name="setup_logging", autouse=True)
def _patch_startup() -> Iterator[MagicMock]:
    with (
        patch("agent_workbench.interfaces.cli.setup_logging") as setup_logging,
        patch("agent_workbench.adapters.ssl_setup.ensure_truststore"),
    ):
        yield setup_logging


@pytest.fixture(name="chat_model")
def _chat_model() -> Iterator[MagicMock]:
    chat_model = MagicMock()
    chat_model.invoke.return_value.content = "OK from model"
    with (
        patch(_LOAD, return_value=_CONFIG),
        patch(_CREATE, return_value=chat_model),
    ):
        yield chat_model


def _report(exit_code: int = 0) -> VerifyReport:
    return VerifyReport(
        config_path=Path("config.toml"),
        config_entries=[{"label": "Config file", "status": "ok", "value": "x"}],
        config_has_error=False,
        backend="openai",
        provider={"backend": {"ok": True, "value": "openai"}, "overall_ok": True},
        test_prompt_error=None,
        install_hints=[],
        exit_code=exit_code,
    )


# --- general ----------------------------------------------------------------


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.startswith("agent-workbench ")


def test_no_subcommand_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 1
    assert "verify" in capsys.readouterr().out


def test_log_level_forwarded_upper(setup_logging: MagicMock) -> None:
    with patch("agent_workbench.services.verify.run_verify", return_value=_report()):
        main(["--log-level", "debug", "verify"])
    setup_logging.assert_called_once_with("DEBUG")


def test_log_level_default_output(setup_logging: MagicMock) -> None:
    with patch("agent_workbench.services.verify.run_verify", return_value=_report()):
        main(["verify"])
    setup_logging.assert_called_once_with("OUTPUT")


# --- verify -----------------------------------------------------------------


@pytest.mark.parametrize("exit_code", [0, 1])
def test_verify_prints_report_and_returns_exit_code(
    exit_code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch(
        "agent_workbench.services.verify.run_verify",
        return_value=_report(exit_code),
    ) as run_verify:
        assert main(["verify"]) == exit_code
    run_verify.assert_called_once_with(check_models=False)
    out = capsys.readouterr().out
    assert "=== CONFIG" in out
    assert "=== LLM PROVIDER DETAILS" in out


def test_verify_check_models_forwarded() -> None:
    with patch(
        "agent_workbench.services.verify.run_verify", return_value=_report()
    ) as run_verify:
        main(["verify", "--check-models"])
    run_verify.assert_called_once_with(check_models=True)


# --- prompt -----------------------------------------------------------------


@pytest.mark.usefixtures("chat_model")
def test_prompt_prints_answer(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["prompt", "hi"]) == 0
    assert capsys.readouterr().out == "OK from model\n"


def test_prompt_timeout_forwarded(chat_model: MagicMock) -> None:
    with (
        patch(_LOAD, return_value=_CONFIG),
        patch(_CREATE, return_value=chat_model) as create,
    ):
        assert main(["prompt", "hi", "--timeout", "5"]) == 0
    create.assert_called_once_with(_CONFIG.as_dict(), timeout=5)


def test_prompt_default_timeout(chat_model: MagicMock) -> None:
    with (
        patch(_LOAD, return_value=_CONFIG),
        patch(_CREATE, return_value=chat_model) as create,
    ):
        main(["prompt", "hi"])
    create.assert_called_once_with(_CONFIG.as_dict(), timeout=60)


def test_prompt_404_logs_hint(
    chat_model: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    chat_model.invoke.side_effect = Exception("404 not found")
    with patch(
        "agent_workbench.adapters.langchain._errors_404._get_model_suggestions",
        return_value="",
    ):
        assert main(["prompt", "hi"]) == 1
        hint = _format_404_hint(_CONFIG.as_dict())
    assert hint in caplog.text


def test_prompt_connection_error(
    chat_model: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    chat_model.invoke.side_effect = ConnectionError("refused")
    assert main(["prompt", "hi"]) == 1
    assert "Prompt command failed" in caplog.text
    assert "refused" in caplog.text


def test_prompt_auth_error(
    chat_model: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    chat_model.invoke.side_effect = LLMAuthError("invalid api key")
    assert main(["prompt", "hi"]) == 1
    assert "invalid api key" in caplog.text


def test_prompt_missing_key(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = LLMConfig(backend="openai", model="gpt-4o-mini")
    with patch(_LOAD, return_value=config):
        assert main(["prompt", "hi"]) == 1
    assert "no api_key in" in caplog.text
    assert "OPENAI_API_KEY" in caplog.text


@pytest.mark.usefixtures("chat_model")
def test_prompt_other_exception(caplog: pytest.LogCaptureFixture) -> None:
    with patch(_LOAD, side_effect=RuntimeError("boom")):
        assert main(["prompt", "hi"]) == 1
    assert "boom" in caplog.text


# --- light --version --------------------------------------------------------

_TOP_LEVEL_MODULES = (
    "agent_workbench.interfaces.cli",
    "agent_workbench.interfaces",
    "agent_workbench.services",
    "agent_workbench.services.logging_setup",
    "agent_workbench.adapters",
    "agent_workbench.core",
)


def _module_file(module: str) -> tuple[Path, str]:
    """Return the source file of *module* and the package relative imports resolve to."""
    root = Path(agent_workbench.__file__).parent.parent
    path = root.joinpath(*module.split("."))
    if path.is_dir():
        return path / "__init__.py", module
    return path.with_suffix(".py"), module.rpartition(".")[0]


def _module_level_imports(tree: ast.Module, package: str) -> list[str]:
    """Return the absolute names imported at module level (outside functions)."""
    names: list[str] = []
    stack: list[ast.AST] = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                anchor = ".".join(parts[: len(parts) - node.level + 1])
                base = f"{anchor}.{base}" if base else anchor
            names.append(base)
            names.extend(f"{base}.{alias.name}" for alias in node.names)
        stack.extend(ast.iter_child_nodes(node))
    return names


@pytest.mark.parametrize("module", _TOP_LEVEL_MODULES)
def test_cli_top_level_imports_skip_model_layer(module: str) -> None:
    path, package = _module_file(module)
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = _module_level_imports(tree, package)
    assert not [name for name in imports if "adapters.langchain" in name]
