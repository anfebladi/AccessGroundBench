"""Unified command-line dispatcher for AccessGroundBench."""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Callable, Sequence

from paths import NoDatasetSpecified

CommandMain = Callable[[list[str] | None], object]

COMMANDS: dict[str, tuple[str, str, str]] = {
    "collect": (
        "collection.cli",
        "collect_main",
        "collect and validate benchmark captures",
    ),
    "evaluate": (
        "evaluation.cli",
        "evaluate_main",
        "evaluate vision-language models",
    ),
    "analyze": (
        "analysis.cli",
        "analyze_main",
        "run statistical analysis",
    ),
    "canonicalize": (
        "evaluation.cli",
        "canonicalize_main",
        "canonicalize stored evaluation results",
    ),
    "rescore": (
        "evaluation.cli",
        "rescore_main",
        "rescore stored model coordinates",
    ),
    "profile": (
        "collection.cli",
        "profile_main",
        "apply or reset an accessibility profile",
    ),
    "capture": (
        "collection.cli",
        "capture_main",
        "capture a screenshot and UI hierarchy",
    ),
    "extract": (
        "collection.cli",
        "extract_main",
        "extract element bounds from UI XML",
    ),
    "ui": (
        "webui.backend.launcher",
        "ui_main",
        "launch the local web UI (needs the 'ui' extra)",
    ),
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agb",
        description="AccessGroundBench collection, evaluation, and analysis tools",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("command", nargs="?", choices=COMMANDS)
    return parser


def _print_help(parser: argparse.ArgumentParser) -> None:
    parser.print_help()
    print("\ncommands:")
    width = max(map(len, COMMANDS))
    for name, (_module, _function, help_text) in COMMANDS.items():
        print(f"  {name:<{width}}  {help_text}")
    print("\nRun 'agb <command> --help' for command-specific options.")


def _load_command(name: str) -> CommandMain:
    module_name, function_name, _help = COMMANDS[name]
    module = importlib.import_module(module_name)
    command = getattr(module, function_name)
    return command


def main(argv: Sequence[str] | None = None) -> object:
    """Dispatch an ``agb`` subcommand without eagerly importing its domain."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()

    if not arguments or arguments[0] in {"-h", "--help"}:
        _print_help(parser)
        return None

    # Parse only the command token. Everything after it belongs verbatim to
    # the selected adapter, including its own ``-h``/``--help`` flags.
    namespace = parser.parse_args(arguments[:1])
    if namespace.command is None:
        _print_help(parser)
        return None

    try:
        return _load_command(namespace.command)(arguments[1:])
    except NoDatasetSpecified as exc:
        # Backstop for the commands that cannot fail at argparse time -- notably
        # `agb analyze`, which legitimately infers its dataset from a --csv
        # sitting beside labels/ and so can only discover the gap afterwards.
        # Printed rather than raised so the web UI's run panel (which spawns
        # cli.main with stderr merged into stdout) shows one line, not a
        # traceback.
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    main()
