from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from typing import Any, Coroutine

import pytest

from iterm2_api_wrapper.client import iTermClient
from iterm2_api_wrapper.state import iTermState

from .conftest import RUN_TIMEOUT, log_var


pytestmark = pytest.mark.skipif(
    str(os.getenv("ITERM2_INTEGRATION", "")).lower() not in {"1", "true", "yes"},
    reason=(
        "Integration tests require iTerm2 running with the Python API enabled. "
        "Set ITERM2_INTEGRATION=1 to run."
    ),
)


def run_coroutine_threadsafe[T](
    coro: Coroutine[Any, Any, T],
    loop: asyncio.AbstractEventLoop,
    run_timeout: float = RUN_TIMEOUT,
) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=run_timeout)


@pytest.fixture(scope="module")
def integration_client() -> Generator[iTermClient[iTermState]]:
    with iTermClient[iTermState](timeout=RUN_TIMEOUT, new_tab=False) as client:
        yield client


def test_client_run_returns_state(integration_client: iTermClient[iTermState]) -> None:
    state = integration_client.get_state()
    assert state.connection is not None
    assert state.app is not None
    assert state.window is not None
    assert state.tab is not None
    assert state.session is not None
    assert state.profile is not None


def test_client_state_methods(integration_client: iTermClient[iTermState]) -> None:
    state = integration_client.get_state()

    async def get_title() -> str:
        return await state.get_tab_var("title")

    async def get_cwd() -> str:
        return await state.get_session_var("path")

    title = run_coroutine_threadsafe(get_title(), integration_client.loop)
    cwd = run_coroutine_threadsafe(get_cwd(), integration_client.loop)

    assert isinstance(title, str)
    assert isinstance(cwd, str)
    log_var("title", title)
    log_var("cwd", cwd)


def test_client_reuses_connection(integration_client: iTermClient[iTermState]) -> None:
    first_state = integration_client.state
    first_connection = integration_client.state.connection

    # Test via state_manager
    state = integration_client.get_state()
    assert state is first_state  # Same state object
    assert state.connection is first_connection
    assert integration_client.state is first_state

    # Test via get_state
    state = integration_client.get_state()
    assert state is first_state
    assert state.connection is first_connection
    assert integration_client.state is first_state

    # Second state_manager call
    state = integration_client.get_state()
    assert state.connection is first_connection
