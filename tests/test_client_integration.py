from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from functools import partial
from pathlib import Path
from typing import Any, Coroutine

import pytest
from dotenv import load_dotenv
from rich.console import Console
from rich.pretty import pprint

from iterm2_api_wrapper.client import iTermClient
from iterm2_api_wrapper.state import iTermState


load_dotenv()
pytestmark = pytest.mark.skipif(
    os.getenv("ITERM2_INTEGRATION", "").lower() not in {"1", "true", "yes"},
    reason=(
        "Integration tests require iTerm2 running with the Python API enabled. "
        "Set ITERM2_INTEGRATION=1 to run."
    ),
)


RUN_TIMEOUT = float(os.getenv("ITERM2_INTEGRATION_TIMEOUT", "60"))
log_path_env = os.getenv("ITERM2_INTEGRATION_LOG")
log_path = (
    Path(log_path_env).expanduser()
    if log_path_env
    else Path(__file__).resolve().parents[1] / "logs" / "pytest.log"
)
log_path.parent.mkdir(parents=True, exist_ok=True)

console = Console(record=True, log_path=True, file=log_path.open("a"))
pp = partial(pprint, console=console, indent_guides=False, expand_all=True)


def run_coroutine_threadsafe[T](
    coro: Coroutine[Any, Any, T], loop: asyncio.AbstractEventLoop
) -> T:
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=RUN_TIMEOUT)


@pytest.fixture(scope="module")
def integration_client() -> Generator[iTermClient[iTermState]]:
    with iTermClient[iTermState](timeout=RUN_TIMEOUT, new_tab=False) as client:
        yield client


def test_client_run_returns_state(integration_client: iTermClient[iTermState]) -> None:
    with integration_client.state_manager(close=False) as state:
        assert state.connection is not None
        assert state.app is not None
        assert state.window is not None
        assert state.tab is not None
        assert state.session is not None
        assert state.profile is not None


def test_client_state_methods(integration_client: iTermClient[iTermState]) -> None:
    with integration_client.state_manager(close=False) as state:

        async def get_title() -> str:
            return await state.get_variable("tab", "title")

        async def get_cwd() -> str | None:
            return await state.get_variable("session", "path")

        title = run_coroutine_threadsafe(get_title(), integration_client.loop)
        cwd = run_coroutine_threadsafe(get_cwd(), integration_client.loop)

        assert isinstance(title, str)
        assert cwd is None or isinstance(cwd, str)
        pp(f"{cwd=}")


def test_client_reuses_connection(integration_client: iTermClient[iTermState]) -> None:
    with integration_client.state_manager(close=False) as first_state:
        assert first_state.connection is first_state.connection

        assert first_state.online is True
        for k, v in first_state.asdict().items():
            if k == "profile":
                continue
            pp({k: v})
