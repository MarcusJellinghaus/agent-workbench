"""Tests for the mcp_coder_utils shims: each re-exports the upstream objects unchanged."""

import importlib

import pytest


@pytest.mark.parametrize(
    ("shim_module", "sources"),
    [
        (
            "agent_workbench.adapters.redaction",
            {
                "mcp_coder_utils.redaction": [
                    "REDACTED_VALUE",
                    "SENSITIVE_KEY_PATTERNS",
                    "token_fingerprint",
                ]
            },
        ),
        (
            "agent_workbench.adapters.tool_spec",
            {
                "mcp_coder_utils.tool_spec": ["ToolCollector", "ToolSpec"],
                "mcp_coder_utils.tool_provider": [
                    "StaticToolset",
                    "Toolset",
                    "ToolsetProvider",
                ],
            },
        ),
        (
            "agent_workbench.adapters.user_app_data",
            {"mcp_coder_utils.user_app_data": ["get_user_app_data_dir"]},
        ),
    ],
)
def test_shim_reexports_upstream_objects(
    shim_module: str, sources: dict[str, list[str]]
) -> None:
    """The shim exports exactly the listed names, each the same object as upstream."""
    shim = importlib.import_module(shim_module)

    assert sorted(shim.__all__) == sorted(
        n for names in sources.values() for n in names
    )
    for source_module, names in sources.items():
        source = importlib.import_module(source_module)
        for name in names:
            assert getattr(shim, name) is getattr(source, name)
