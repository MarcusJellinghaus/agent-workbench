"""Toolset building shared by ``get_runtime`` and the ``agent-workbench-ui`` gate."""

from agent_workbench.adapters import tools, toolset_providers
from agent_workbench.adapters.config import ConfigFile
from agent_workbench.services import logging_setup


def clamp_provider_loggers(config_file: ConfigFile) -> None:
    """Clamp the loggers of the configured providers' top-level packages to ``INFO``.

    The packages come from the entry points without loading them; names without an
    entry point are skipped (they fail in the build).

    Args:
        config_file: The read config file.
    """
    logging_setup.clamp_loggers(toolset_providers.provider_packages(config_file.tools))


def build_configured_toolsets(config_file: ConfigFile) -> tools.Toolsets | None:
    """Clamp the provider loggers, then build the toolsets of every ``[tools.<name>]``.

    ``build_toolsets`` errors propagate; a non-table ``[tools]`` reaches it too, so
    there is no silent run without tools.

    Args:
        config_file: The read config file.

    Returns:
        The built toolsets, or None without a ``[tools]`` table.
    """
    if not config_file.tools and not config_file.tools_type_error:
        return None
    clamp_provider_loggers(config_file)
    return tools.build_toolsets(config_file)
