"""Top-level package for Iterm2 Scripts."""

from .client import create_iterm_client
from .state import iTermState

__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"


__all__ = [
    "create_iterm_client",
    "iTermState",
]
