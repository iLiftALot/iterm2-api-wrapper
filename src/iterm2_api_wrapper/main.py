import sys
from typing import Unpack

from iterm2_api_wrapper.api.it2api import create_iterm_state
from iterm2_api_wrapper.api.it2connection import run_until_complete
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.typings import iTermSetupKwargs


def init(retry: bool, **kwargs: Unpack[iTermSetupKwargs]) -> iTermState:
    """Main function to run iTerm2 setup."""

    global_state: iTermState = run_until_complete(create_iterm_state, retry, **kwargs)  # ty:ignore[invalid-argument-type]]
    return global_state


if __name__ == "__main__":
    debug, new_tab = ["--debug" in sys.argv[1:], "--new_tab" in sys.argv[1:]]
    global_state: iTermState = init(retry=True, debug=debug, new_tab=new_tab)
    init(retry=False, dedicated_profile_name="", debug=True, new_tab=False)
