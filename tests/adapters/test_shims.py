"""Tests for the mcp_coder_utils shims: each re-exports the upstream objects unchanged."""

import importlib

import pytest


@pytest.mark.parametrize(
    ("shim_module", "source_module", "names"),
    [
        (
            "agent_workbench.adapters.redaction",
            "mcp_coder_utils.redaction",
            ["REDACTED_VALUE", "SENSITIVE_KEY_PATTERNS", "token_fingerprint"],
        ),
        (
            "agent_workbench.adapters.tool_spec",
            "mcp_coder_utils.tool_spec",
            ["ToolCollector", "ToolSpec"],
        ),
        (
            "agent_workbench.adapters.user_app_data",
            "mcp_coder_utils.user_app_data",
            ["get_user_app_data_dir"],
        ),
    ],
)
def test_shim_reexports_upstream_objects(
    shim_module: str, source_module: str, names: list[str]
) -> None:
    """The shim exports exactly `names`, each the same object as in the source module."""
    shim = importlib.import_module(shim_module)
    source = importlib.import_module(source_module)

    assert sorted(shim.__all__) == sorted(names)
    for name in names:
        assert getattr(shim, name) is getattr(source, name)
