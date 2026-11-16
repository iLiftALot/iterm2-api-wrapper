"""Top-level package for Iterm2 Scripts."""
# ruff: file-ignore[non-empty-init-module, module-import-not-at-top-of-file]

from __future__ import annotations


__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"


from dotenv import load_dotenv


load_dotenv()

from .utils.logger import get_logger


logger = get_logger()
logger.disable(__package__)

from .api.it2api import create_iterm_state, iTermAPI
from .api.it2connection import Connection as iTermConnection
from .core.client import (
    close_all_shared_clients,
    close_shared_client,
    create_iterm_client,
    get_shared_client,
    iTermClient,
)
from .core.typings import CommandExecutionResult, CommandExecutionStatus, CommandExitCode
from .state import iTermState


logger.debug("Initializing package: {}", __package__)


__all__ = [
    "CommandExecutionResult",
    "CommandExecutionStatus",
    "CommandExitCode",
    "close_all_shared_clients",
    "close_shared_client",
    "create_iterm_client",
    "create_iterm_state",
    "get_logger",
    "get_shared_client",
    "iTermAPI",
    "iTermClient",
    "iTermConnection",
    "iTermState",
    "logger",
]
