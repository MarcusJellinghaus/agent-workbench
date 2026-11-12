"""The tool path (config → toolsets → filter → log → LangChain tool) never imports ``mcp``.

Top level: it spans adapters and services. The per-package guarantee lives in the
providers' own tests; this one covers agent-workbench's modules on the same path.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_workbench.adapters.toolset_providers import registered_providers

_SRC = Path(__file__).resolve().parents[1] / "src"

# Imports only the modules of the tool path, never agent_workbench.apps.
_SCRIPT = """\
import asyncio
import sqlite3
import sys
from pathlib import Path

from agent_workbench.adapters import config
from agent_workbench.adapters.tools import build_toolsets, to_structured_tool
from agent_workbench.services.tool_call_log import wrap_spec
from agent_workbench.services.tool_filter import enabled_specs

tmp = Path(sys.argv[1])
config.app_data_dir = lambda: tmp
db = tmp / "test.db"
with sqlite3.connect(db) as conn:
    conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY)")
conn.close()
query_config = tmp / "mcp-tools-sql.toml"
query_config.write_text('connection = "default"\\n', encoding="utf-8")
database_config = tmp / "db.toml"
database_config.write_text(
    f'[connections.default]\\nbackend = "sqlite"\\npath = "{db.as_posix()}"\\n',
    encoding="utf-8",
)
workspace = tmp / "workspace"
workspace.mkdir()
config_path = tmp / "config.toml"
config_path.write_text(
    f'[tools.sql]\\nquery_config = "{query_config.as_posix()}"\\n'
    f'database_config = "{database_config.as_posix()}"\\n\\n'
    f'[tools.workspace]\\nproject_dir = "{workspace.as_posix()}"\\n',
    encoding="utf-8",
)
toolsets = build_toolsets(config.read_config_file(config_path))
try:
    tools = {
        spec.name: to_structured_tool(wrap_spec(spec))
        for spec in enabled_specs(toolsets.specs)
    }
    asyncio.run(tools["read_tables"].ainvoke({"schema": "main"}))
    asyncio.run(tools["list_directory"].ainvoke({}))
finally:
    toolsets.close()
print("mcp" in sys.modules or any(m.startswith("mcp.") for m in sys.modules))
"""


@pytest.mark.integration
@pytest.mark.skipif(
    not {"sql", "workspace"}.issubset(registered_providers()),
    reason="toolset providers 'sql' and 'workspace' are not installed",
)
def test_tool_path_does_not_import_mcp(tmp_path: Path) -> None:
    """Building, wrapping, adapting and calling the real tools imports no ``mcp``."""
    script = tmp_path / "tool_path_probe.py"
    script.write_text(_SCRIPT, encoding="utf-8")

    # Not a fresh env: Windows needs SYSTEMROOT and the rest of the environment.
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(script), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )

    assert result.returncode == 0, result.stderr[-4000:]
    assert result.stdout.strip() == "False"
