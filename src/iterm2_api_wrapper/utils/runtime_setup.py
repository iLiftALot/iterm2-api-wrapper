from __future__ import annotations

from typing import TYPE_CHECKING

from iterm2.capabilities import check_supports_get_default_profile, check_supports_prompt_id

from .._logging import PrettyLog
from ..api.it2prompt import check_supports_prompt_monitor_modes


if TYPE_CHECKING:
    from ..gateway import _Connection


log = PrettyLog.get_logger(__name__)


def _install_iterm2_connection_bridge() -> None:
    """Expose the wrapper connection implementation through upstream public APIs."""
    import iterm2
    import iterm2.connection as upstream_connection

    from ..api import it2connection as wrapper_connection

    previous_connection = upstream_connection.Connection

    # Preserve notification helpers registered before the bridge was installed.
    if previous_connection is not wrapper_connection.Connection:
        for helper in previous_connection.helpers:
            if helper not in wrapper_connection.Connection.helpers:
                wrapper_connection.Connection.helpers.append(helper)

    # Preserve callbacks registered before bridge installation and ensure that
    # old upstream callback functions still resolve the wrapper-owned registry.
    if upstream_connection.gDisconnectCallbacks is not wrapper_connection.gDisconnectCallbacks:
        for callback in upstream_connection.gDisconnectCallbacks:
            if callback not in wrapper_connection.gDisconnectCallbacks:
                wrapper_connection.gDisconnectCallbacks.append(callback)

        upstream_connection.gDisconnectCallbacks = wrapper_connection.gDisconnectCallbacks

    upstream_connection.Connection = wrapper_connection.Connection
    upstream_connection.run_until_complete = wrapper_connection.run_until_complete
    upstream_connection.run_forever = wrapper_connection.run_forever
    upstream_connection.add_disconnect_callback = wrapper_connection.add_disconnect_callback

    iterm2.Connection = wrapper_connection.Connection
    iterm2.run_until_complete = wrapper_connection.run_until_complete
    iterm2.run_forever = wrapper_connection.run_forever
    iterm2.add_disconnect_callback = wrapper_connection.add_disconnect_callback


def _enhance_imports() -> None:
    """Inject the iTerm2 package root with `__all__` for importing convenience."""
    import iterm2

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
    updated_contents = existing_contents + f"\n\n\n__all__ = {json.dumps(sorted(iterm2_exported_names), indent=4)}\n"
    package_root_path.write_text(updated_contents)


def _check_version(connection: _Connection) -> None:
    """Validate the capabilities required by iTermAPI for this connection."""
    check_supports_prompt_monitor_modes(connection)  # Protocol 1.1
    check_supports_get_default_profile(connection)  # Protocol 1.4
    check_supports_prompt_id(connection)  # Protocol 1.5

    major_version, minor_version = connection.iterm2_protocol_version
    log.debug(f"iTerm protocol version {major_version}.{minor_version}")


def validate_iterm2_runtime(connection: _Connection) -> None:
    """..."""
    _enhance_imports()
    _install_iterm2_connection_bridge()
    _check_version(connection)
