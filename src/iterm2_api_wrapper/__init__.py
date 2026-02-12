"""Top-level package for Iterm2 Scripts."""
# ruff: noqa: E402

__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"

from dotenv import load_dotenv

from .logging import PrettyLog


load_dotenv(override=True)
log = PrettyLog(
    __package__,
    mode="all",
    level="DEBUG",
    pretty_config={
        "file_console_config": {"emoji": True, "tab_size": 4},
        "logger_config": {"justify": "left"},
        "terminal_console_config": {"emoji": True, "tab_size": 4},
        "file_manager_config": {"clear_file_on_init": True},
    },
)


from .client import create_iterm_client
from .state import iTermState


__all__ = ["create_iterm_client", "iTermState"]
