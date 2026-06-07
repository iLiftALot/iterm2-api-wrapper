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


from .client import ITermClient, create_iterm_client, get_shared_client
from .api import iTermAPI, create_iterm_state
from .state import iTermState
from .typings import CommandExitCode, CommandStatus


type iTermClient = ITermClient

__all__ = [
    "CommandExitCode",
    "CommandStatus",
    "ITermClient",
    "create_iterm_client",
    "create_iterm_state",
    "get_shared_client",
    "iTermAPI",
    "iTermClient",
    "iTermState",
    "log",
]
