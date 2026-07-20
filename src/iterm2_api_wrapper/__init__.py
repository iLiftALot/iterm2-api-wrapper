"""Top-level package for Iterm2 Scripts."""

# ruff: noqa: E402
from __future__ import annotations


__package__ = "iterm2_api_wrapper"
__author__ = "Nicholas Corbin"
__email__ = "nickcorbin17@yahoo.com"


from dotenv import load_dotenv

from ._logging import PrettyLog, get_default_log_config


load_dotenv()
logger = PrettyLog(__package__)


from typing import TYPE_CHECKING

from .api.it2api import create_iterm_state, iTermAPI
from .client import close_all_shared_clients, close_shared_client, create_iterm_client, get_shared_client, iTermClient
from .state import iTermState
from .typings import CommandExecutionStatus, CommandExitCode, iTermConnection


if TYPE_CHECKING:
    from .gateway import _Connection


_BOOTSTRAPPED: bool = False


def validate_iterm2_runtime(connection: _Connection) -> None:
    global _BOOTSTRAPPED

    if _BOOTSTRAPPED is True:
        return

    import iterm2

    def enhance_it2_imports() -> None:
        """Inject the iTerm2 package root with `__all__` for importing convenience."""
        if getattr(iterm2, "__all__", None) is not None:
            return

        import json
        from pathlib import Path
        from types import ModuleType

        iterm2_exported_names: list[str] = []
        for name in dir(iterm2):
            attr = getattr(iterm2, name)
            if isinstance(attr, ModuleType) or (name.startswith("__") and name != "__version__"):
                continue

            iterm2_exported_names.append(name)

        package_root_path = Path(iterm2.__file__)
        existing_contents = package_root_path.read_text().rstrip()
        updated_contents = (
            existing_contents + f"\n\n\n__all__ = {json.dumps(sorted(iterm2_exported_names), indent=4)}\n"
        )
        package_root_path.write_text(updated_contents)

    def install_it2_connection_bridge() -> None:
        """Make upstream :class:`iterm2.Connection` exports point at this package's Connection."""
        import iterm2.connection as upstream_connection

        from .api.it2connection import Connection, add_disconnect_callback, run_forever, run_until_complete

        upstream_connection.Connection = Connection
        upstream_connection.run_until_complete = run_until_complete
        upstream_connection.run_forever = run_forever
        upstream_connection.add_disconnect_callback = add_disconnect_callback

        iterm2.Connection = Connection
        iterm2.run_until_complete = run_until_complete
        iterm2.run_forever = run_forever
        iterm2.add_disconnect_callback = add_disconnect_callback

    def check_it2_versioning(connection: _Connection) -> None:
        """Check if the iTerm app meets the minimum required API capabilities before setup continues."""
        from iterm2 import capabilities

        from .api.it2prompt import check_supports_prompt_monitor_modes

        check_supports_prompt_monitor_modes(connection)  # 1.1
        capabilities.check_supports_get_default_profile(connection)  # 1.4
        capabilities.check_supports_prompt_id(connection)  # 1.5

        major_version, minor_version = connection.iterm2_protocol_version
        logger.debug(f":check: iTerm protocol version {major_version}.{minor_version} >= {1.6}", emoji=True)

    enhance_it2_imports()
    install_it2_connection_bridge()
    check_it2_versioning(connection)

    _BOOTSTRAPPED = True


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
