"""Command-line entry point for agent-workbench."""

import argparse
import logging
import sys
from importlib.metadata import PackageNotFoundError, version

from agent_workbench.services.logging_setup import LOG_LEVELS, setup_logging

logger = logging.getLogger(__name__)


def _package_version() -> str:
    """Return the installed package version, or "unknown" when not installed."""
    try:
        return version("agent-workbench")
    except PackageNotFoundError:
        return "unknown"


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        The parser with the ``verify`` and ``prompt`` subcommands.
    """
    parser = argparse.ArgumentParser(prog="agent-workbench", description=__doc__)
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_package_version()}"
    )
    parser.add_argument(
        "--log-level",
        type=str.upper,
        choices=LOG_LEVELS,
        default="OUTPUT",
        metavar="LEVEL",
        help=f"logging level: {', '.join(LOG_LEVELS)} (default: OUTPUT)",
    )
    subparsers = parser.add_subparsers(dest="command")

    verify = subparsers.add_parser(
        "verify", help="check config, LLM provider and a live test prompt"
    )
    verify.add_argument(
        "--check-models",
        action="store_true",
        help="also list the backend's available models",
    )

    prompt = subparsers.add_parser("prompt", help="send one prompt to the LLM")
    prompt.add_argument("prompt", help="the prompt text")
    prompt.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="request timeout in seconds (default: 60)",
    )
    return parser


def _run_verify(args: argparse.Namespace) -> int:
    """Run ``verify`` and print the report.

    Returns:
        The report's exit code.
    """
    from agent_workbench.interfaces.verify_formatting import format_report
    from agent_workbench.services.verify import run_verify

    report = run_verify(check_models=args.check_models)
    print(format_report(report))
    return report.exit_code


def _run_prompt(args: argparse.Namespace) -> int:
    """Send one prompt and print the answer.

    Returns:
        0 on success, 1 on any error.
    """
    from agent_workbench.adapters import config as config_adapter
    from agent_workbench.adapters import llm

    try:
        config = config_adapter.load_llm_config()
        chat_model = llm.create_chat_model(config, args.timeout)
        print(llm.invoke(chat_model, config, args.prompt))
        return 0
    except Exception as exc:  # pylint: disable=broad-exception-caught  # top-level CLI error boundary
        logger.error("Prompt command failed: %s", exc)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    # Ensure stdout/stderr use UTF-8 on all platforms (e.g. Windows cp1252 default).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = _build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_level)

    from agent_workbench.adapters.ssl_setup import ensure_truststore

    ensure_truststore()

    if args.command == "verify":
        return _run_verify(args)
    if args.command == "prompt":
        return _run_prompt(args)
    parser.print_help()
    return 1
