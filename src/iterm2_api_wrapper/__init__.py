"""Top-level package for Iterm2 Scripts."""
# ruff: noqa: E402

__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"

from dotenv import load_dotenv

from .logging import PrettyLog, get_default_log_config


load_dotenv()
log = PrettyLog(
    __package__, mode="all", level="DEBUG", pretty_config=get_default_log_config()
)


from .client import create_iterm_client, get_shared_client
from .state import iTermState


__all__ = ["create_iterm_client", "get_shared_client", "iTermState"]
