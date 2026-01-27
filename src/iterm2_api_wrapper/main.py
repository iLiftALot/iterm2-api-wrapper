from __future__ import annotations

import sys
from typing import Unpack

from iterm2_api_wrapper.param_types import iTermSetupKwargs
from iterm2_api_wrapper.runtime_setup import run_iterm_setup
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.utils import run_until_complete  # , pp


def init(retry: bool, **kwargs: Unpack[iTermSetupKwargs]) -> iTermState:
    """Main function to run iTerm2 setup."""

    global_state: iTermState = run_until_complete(run_iterm_setup, retry, **kwargs)
    return global_state


if __name__ == "__main__":
    debug = "--debug" in sys.argv[1:]
    global_state: iTermState = init(
        retry=True, debug=debug, new_tab=False, select_tab=True, order_window_front=False
    )
