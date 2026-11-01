from __future__ import annotations

from typing import TYPE_CHECKING, cast


if TYPE_CHECKING:
    from iterm2.connection import Connection as UpstreamConnection

    from ..core.gateway import Connection


def _as_upstream_connection(connection: Connection | UpstreamConnection) -> UpstreamConnection:
    """Expose the protocol transport at iTerm2's nominal typing boundary.

    Upstream RPCs use the same send/dispatch contract, and runtime setup installs
    our independent Connection as the upstream connection implementation. This
    cast changes neither the object nor its modern websocket transport.
    """
    return cast("UpstreamConnection", connection)
