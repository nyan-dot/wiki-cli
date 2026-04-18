from __future__ import annotations

import argparse
import logging
import sys
import time
import urllib.error

from .activity import command_arguments, log_activity
from .commands import COMMAND_PARSER_REGISTRARS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Tools for maintaining a local LLM wiki."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for register in COMMAND_PARSER_REGISTRARS:
        register(subparsers)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    start_time = time.perf_counter()

    log_activity(
        "command_started",
        command_name=args.command,
        arguments=command_arguments(args),
    )

    try:
        args.func(args)
    except urllib.error.URLError as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_activity(
            "command_failed",
            level=logging.ERROR,
            command_name=args.command,
            arguments=command_arguments(args),
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        print(f"Network error: {exc}", file=sys.stderr)
        return 1
    except (FileExistsError, FileNotFoundError, ValueError) as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_activity(
            "command_failed",
            level=logging.ERROR,
            command_name=args.command,
            arguments=command_arguments(args),
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=str(exc),
            exc_info=True,
        )
        print(str(exc), file=sys.stderr)
        return 1

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    log_activity(
        "command_completed",
        command_name=args.command,
        arguments=command_arguments(args),
        duration_ms=duration_ms,
    )
    return 0
