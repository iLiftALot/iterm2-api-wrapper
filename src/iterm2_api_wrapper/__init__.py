"""Top-level package for Iterm2 Scripts."""

# ruff: noqa: E402
from __future__ import annotations

import os


__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"


from dotenv import load_dotenv


load_dotenv()

from ._logging import PrettyLog, get_default_log_config


logger = PrettyLog(__package__, level="DEBUG" if os.getenv("IT2_DEBUG") else "INFO")


from .api.it2api import create_iterm_state, iTermAPI
from .api.it2connection import Connection as iTermConnection
from .core.client import (
    close_all_shared_clients,
    close_shared_client,
    create_iterm_client,
    get_shared_client,
    iTermClient,
)
from .core.typings import CommandExecutionStatus, CommandExitCode
from .state import iTermState


__all__ = [
    "CommandExecutionStatus",
    "CommandExitCode",
    "PrettyLog",
    "close_all_shared_clients",
    "close_shared_client",
    "create_iterm_client",
    "create_iterm_state",
    "get_default_log_config",
    "get_shared_client",
    "iTermAPI",
    "iTermClient",
    "iTermConnection",
    "iTermState",
    "logger",
]
