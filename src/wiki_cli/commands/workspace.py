from __future__ import annotations

import argparse

from .. import paths
from ..activity import log_activity


def init_command() -> None:
    paths.ensure_workspace()
    log_activity("workspace_initialized", command_name="init")
    print("Workspace directories are ready.")


def register_init_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    init_parser = subparsers.add_parser(
        "init", help="Create required workspace directories."
    )
    init_parser.set_defaults(func=lambda _args: init_command())
