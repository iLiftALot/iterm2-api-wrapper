from __future__ import annotations

import asyncio
from typing import Any, cast

from pytest import MonkeyPatch

from iterm2_api_wrapper.api import it2app, Connection
from iterm2_api_wrapper.api.it2app import App, async_get_app


def test_async_get_app_returns_none_when_creation_disabled(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(it2app.app.App, "instance", None, raising=False)

    result = asyncio.run(async_get_app(cast(Any, "conn"), create_if_needed=False))

    assert result is None


def test_async_get_app_refreshes_existing_wrapper(monkeypatch: MonkeyPatch) -> None:
    wrapper = object.__new__(App)
    calls: list[str] = []

    async def async_refresh() -> None:
        calls.append("refresh")

    monkeypatch.setattr(wrapper, "async_refresh", async_refresh)
    monkeypatch.setattr(it2app.app.App, "instance", wrapper, raising=False)

    result = asyncio.run(async_get_app(cast(Connection, "conn")))

    assert result is wrapper
    assert calls == ["refresh"]


def test_async_get_app_replaces_upstream_singleton(monkeypatch: MonkeyPatch) -> None:
    wrapper = object.__new__(App)
    constructed_with: list[Any] = []
    callbacks: list[Any] = []

    async def async_construct(connection: Any) -> App:
        constructed_with.append(connection)
        return wrapper

    monkeypatch.setattr(App, "async_construct", staticmethod(async_construct))
    monkeypatch.setattr(it2app, "add_disconnect_callback", callbacks.append)
    monkeypatch.setattr(it2app.app.App, "instance", object(), raising=False)

    result = asyncio.run(async_get_app(cast(Connection, "conn")))

    assert result is wrapper
    assert it2app.app.App.instance is wrapper
    assert constructed_with == ["conn"]
    assert callbacks == [it2app.app.invalidate_app]


def test_async_get_app_constructs_missing_singleton(monkeypatch: MonkeyPatch) -> None:
    wrapper = object.__new__(App)
    callbacks: list[Any] = []

    async def async_construct(connection: Any) -> App:
        assert connection == "conn"
        return wrapper

    monkeypatch.setattr(App, "async_construct", staticmethod(async_construct))
    monkeypatch.setattr(it2app, "add_disconnect_callback", callbacks.append)
    monkeypatch.setattr(it2app.app.App, "instance", None, raising=False)

    result = asyncio.run(async_get_app(cast(Connection, "conn")))

    assert result is wrapper
    assert it2app.app.App.instance is wrapper
    assert callbacks == [it2app.app.invalidate_app]


def test_async_refresh_focus_suppresses_nested_refresh() -> None:
    wrapper = object.__new__(App)
    wrapper._focus_refresh_in_progress = True
    wrapper._nested_focus_refresh_skips = 0

    asyncio.run(wrapper.async_refresh_focus())

    assert wrapper._focus_refresh_in_progress is True
    assert wrapper._nested_focus_refresh_skips == 1


def test_async_refresh_focus_resets_guard_after_nested_skip(monkeypatch: MonkeyPatch) -> None:
    wrapper = object.__new__(App)
    wrapper._focus_refresh_in_progress = False
    wrapper._nested_focus_refresh_skips = 0
    calls: list[str] = []

    async def base_refresh(self: App) -> None:
        calls.append("base")
        await self.async_refresh_focus()

    monkeypatch.setattr(it2app.app.App, "async_refresh_focus", base_refresh)

    asyncio.run(wrapper.async_refresh_focus())

    assert calls == ["base"]
    assert wrapper._focus_refresh_in_progress is False
    assert wrapper._nested_focus_refresh_skips == 0
