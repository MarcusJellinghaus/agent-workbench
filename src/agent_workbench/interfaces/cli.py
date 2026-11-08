"""Command-line entry point for agent-workbench."""

import argparse
from importlib.metadata import PackageNotFoundError, version

from agent_workbench.core.greeting import greet


def _package_version() -> str:
    """Return the installed package version, or "unknown" when not installed."""
    try:
        return version("agent-workbench")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="agent-workbench", description=__doc__)
    parser.add_argument("--name", default="world", help="who to greet")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_package_version()}"
    )
    args = parser.parse_args(argv)
    print(greet(args.name))
    return 0
