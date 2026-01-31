from __future__ import annotations

import asyncio
import errno

import pytest

from iterm2_api_wrapper.gateway import _async_create_connection_with_retry


class FlakyConnection:
    """Fake Connection that fails a few times before succeeding."""

    attempts = 0

    @classmethod
    async def async_create(cls):
        cls.attempts += 1
        if cls.attempts < 3:
            raise ConnectionRefusedError(errno.ECONNREFUSED, "connection refused")
        return "ok"


class AlwaysRefusesConnection:
    attempts = 0

    @classmethod
    async def async_create(cls):
        cls.attempts += 1
        raise ConnectionRefusedError(errno.ECONNREFUSED, "connection refused")


class FatalConnection:
    attempts = 0

    @classmethod
    async def async_create(cls):
        cls.attempts += 1
        raise OSError(errno.EPERM, "nope")


def test_async_create_connection_with_retry_retries_then_succeeds() -> None:
    FlakyConnection.attempts = 0

    result = asyncio.run(
        _async_create_connection_with_retry(
            FlakyConnection, timeout_s=1.0, initial_delay_s=0.0, max_delay_s=0.0
        )
    )

    assert result == "ok"
    assert FlakyConnection.attempts == 3


def test_async_create_connection_with_retry_times_out() -> None:
    AlwaysRefusesConnection.attempts = 0

    with pytest.raises(TimeoutError):
        asyncio.run(
            _async_create_connection_with_retry(
                AlwaysRefusesConnection,
                timeout_s=0.0,
                initial_delay_s=0.0,
                max_delay_s=0.0,
            )
        )

    assert AlwaysRefusesConnection.attempts == 1


def test_async_create_connection_with_retry_does_not_retry_fatal_oserror() -> None:
    FatalConnection.attempts = 0

    with pytest.raises(OSError):
        asyncio.run(
            _async_create_connection_with_retry(
                FatalConnection, timeout_s=1.0, initial_delay_s=0.0, max_delay_s=0.0
            )
        )

    assert FatalConnection.attempts == 1
