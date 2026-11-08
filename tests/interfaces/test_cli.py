import pytest

from agent_workbench.interfaces.cli import main


def test_main_prints_greeting(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--name", "Marcus"]) == 0
    assert capsys.readouterr().out == "Hello, Marcus!\n"


def test_main_default_name(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert capsys.readouterr().out == "Hello, world!\n"


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert capsys.readouterr().out.startswith("agent-workbench ")
