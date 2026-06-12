"""Top-level package for Iterm2 Scripts."""
# ruff: noqa: E402

__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"

from dotenv import load_dotenv

# from . import triggers
from ._logging import PrettyLog, get_default_log_config


load_dotenv()
log = PrettyLog(__package__, mode="all", level="DEBUG", pretty_config=get_default_log_config())


from .api import create_iterm_state, iTermAPI
from .client import create_iterm_client, get_shared_client, iTermClient
from .state import iTermState
from .typings import CommandExitCode, CommandStatus


__all__ = [
    "CommandExitCode",
    "CommandStatus",
    "create_iterm_client",
    "create_iterm_state",
    "get_shared_client",
    "iTermAPI",
    "iTermClient",
    "iTermState",
    "log",
]
