from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType

import iterm2
from iterm2.capabilities import check_supports_get_default_profile, check_supports_prompt_id

from .._logging import PrettyLog
from .it2connection import Connection, add_disconnect_callback, run_forever, run_until_complete
from .it2prompt import check_supports_prompt_monitor_modes


log = PrettyLog.get_logger(__name__)
_BOOTSTRAPPED: bool = False


async def bootstrap_iterm2_runtime(*, enhance_imports: bool | None = None) -> None:
    """Install runtime patches that must happen before iTerm2 API setup.

    This should run before app readiness checks, connection creation, and
    monitor registration. It is intentionally idempotent.
    """
    global _BOOTSTRAPPED

    if _BOOTSTRAPPED:
        return

    _install_iterm2_connection_bridge()

    if enhance_imports is None:
        enhance_imports = os.getenv("IT2_ENHANCE_IMPORTS", "").strip().lower() in {"1", "true", "yes", "on"}

    if enhance_imports:
        _enhance_iterm2_imports()

    _BOOTSTRAPPED = True


def validate_iterm2_runtime(connection: Connection) -> None:
    """Validate connected iTerm2 runtime capabilities before setup continues."""
    _validate_app_version(connection)


def _enhance_iterm2_imports() -> None:
    """Inject the iTerm2 package root with `__all__`.

    This mutates the installed dependency and should be treated as a dev-only
    convenience, not normal runtime behavior.
    """
    if getattr(iterm2, "__all__", None) is not None:
        return

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


def _install_iterm2_connection_bridge() -> None:
    """Make upstream `iterm2.connection` exports point at this package's Connection."""
    import iterm2.connection as upstream_connection

    upstream_connection.Connection = Connection
    upstream_connection.run_until_complete = run_until_complete
    upstream_connection.run_forever = run_forever
    upstream_connection.add_disconnect_callback = add_disconnect_callback

    iterm2.Connection = Connection
    iterm2.run_until_complete = run_until_complete
    iterm2.run_forever = run_forever
    iterm2.add_disconnect_callback = add_disconnect_callback


def _validate_app_version(connection: Connection) -> None:
    """Check if the iTerm app meets the minimum required API capabilities."""
    check_supports_prompt_monitor_modes(connection)  # 1.1
    check_supports_get_default_profile(connection)  # 1.4
    check_supports_prompt_id(connection)  # 1.5

    major_version, minor_version = connection.iterm2_protocol_version
    log.debug(f"iTerm version >= minimum required version: {major_version}.{minor_version}")
