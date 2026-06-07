from __future__ import annotations

import os
from typing import Literal, Unpack

from iterm2.capabilities import (
    check_supports_apply_layout,
    check_supports_get_default_profile,
    check_supports_prompt_id,
)

from iterm2_api_wrapper._logging import PrettyLog
from iterm2_api_wrapper.connection import Connection
from iterm2_api_wrapper.state import iTermState
from iterm2_api_wrapper.typings import iTermSetupKwargs, check_supports_prompt_monitor_modes


log = PrettyLog.get_logger(__name__)


def _validate_app_version(connection: Connection) -> None:
    """Check if the iTerm app meets the minimum threshold (1.14 with apply layout)"""
    check_supports_prompt_monitor_modes(connection)
    check_supports_get_default_profile(connection)
    check_supports_prompt_id(connection)
    check_supports_apply_layout(connection)

    major_version, minor_version = connection.iterm2_protocol_version
    log.debug(f"iTerm version >= minimum required version: {major_version}.{minor_version}")


async def _setup_iterm(connection: Connection, **kwargs: Unpack[iTermSetupKwargs]) -> iTermState:
    """Compatibility wrapper for the enhanced class-based iTerm API setup."""
    from iterm2_api_wrapper.api import create_iterm_state

    return await create_iterm_state(
        connection,
        profile_name=kwargs.get("dedicated_profile_name") or os.getenv("ITERM_DEDICATED_PROFILE", None),
        **kwargs,
    )


async def run_iterm_setup(connection: Connection, **kwargs: Unpack[iTermSetupKwargs]) -> iTermState:
    """Run iTerm2 setup. This can also be called directly."""
    _validate_app_version(connection)

    env_debug = os.getenv("ITERM_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
    debug_enabled = kwargs.get("debug", None) or env_debug
    log_level: Literal["DEBUG", "INFO"] = "DEBUG" if debug_enabled else "INFO"
    log.parent.set_level(log_level, propagate=True)
    global_iterm_state: iTermState = await _setup_iterm(connection=connection, **kwargs)

    return global_iterm_state
