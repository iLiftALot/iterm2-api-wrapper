import sys


if sys.version_info >= (3, 12):
    from typing import Unpack
else:
    from typing_extensions import Unpack

from iterm2_api_wrapper.api.it2api import create_iterm_state
from iterm2_api_wrapper.api.it2connection import run_until_complete
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.typings import iTermStateSetupKwargs


__all__ = ["create_iterm_state", "init", "run_until_complete"]


def init(retry: bool, **kwargs: Unpack[iTermStateSetupKwargs]) -> iTermState:
    """Main function to run iTerm2 setup."""

    global_state: iTermState = run_until_complete(create_iterm_state, retry, **kwargs)
    return global_state


if __name__ == "__main__":
    debug, new_tab = ["--debug" in sys.argv[1:], "--new_tab" in sys.argv[1:]]
    global_state: iTermState = init(retry=True, debug=debug, new_tab=new_tab)
    init(retry=False, dedicated_profile_name="", debug=True, new_tab=False)
