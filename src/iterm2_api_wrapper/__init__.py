"""Top-level package for Iterm2 Scripts."""
# ruff: noqa: E402

__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"

from dotenv import load_dotenv

from ._logging import PrettyLog, get_default_log_config


load_dotenv()
logger = PrettyLog(__package__)

from .api import create_iterm_state, iTermAPI
from .client import close_all_shared_clients, close_shared_client, create_iterm_client, get_shared_client, iTermClient
from .state import iTermState
from .typings import CommandExecutionStatus, CommandExitCode, iTermConnection


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
