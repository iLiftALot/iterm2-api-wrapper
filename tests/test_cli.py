from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
import typer

from iterm2_api_wrapper import cli


if TYPE_CHECKING:
    from typer import Context

    from iterm2_api_wrapper.state import iTermState
else:
    Context = iTermState = object


def as_ctx(ctx: object) -> Context:
    return cast(Context, ctx)


def as_state(state: object) -> iTermState:
    return cast(iTermState, state)


def test_kwarg_conversion_splits_args_and_key_value_pairs() -> None:
    args, kwargs = cli.kwarg_conversion(("plain", "name=Alice", "path=/tmp/a=b"))

    assert args == ("plain",)
    assert kwargs == {"name": "Alice", "path": "/tmp/a=b"}


def test_func_to_args_completion_returns_remaining_function_parameters() -> None:
    ctx = as_ctx(SimpleNamespace(params={"func_name": "send_command", "args": ("command='",)}))

    completions = cli.func_to_args_completion("pa", ctx)

    assert ("path='", "path: 'str | None' = None (positional or keyword)") in completions
    assert cli.func_to_args_completion("", as_ctx(SimpleNamespace(params={"func_name": "missing"}))) == []


def test_run_coro_executes_on_supplied_loop() -> None:
    async def scenario() -> str:
        return "done"

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    try:
        assert cli.run_coro(scenario(), loop) == "done"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=2)
        loop.close()


def test_profiles_completion_filters_profile_names(monkeypatch: pytest.MonkeyPatch) -> None:
    profiles = [SimpleNamespace(name="Default", guid="1"), SimpleNamespace(name="Dev", guid="2")]
    monkeypatch.setattr(cli, "run_until_complete", lambda fn: profiles)

    assert cli.profiles_completion("De", as_ctx(SimpleNamespace())) == [
        ("Default", "Profile: Default (1)"),
        ("Dev", "Profile: Dev (2)"),
    ]


def test_send_command_uses_default_command_and_resolves_path() -> None:
    class FakeState:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def run_command(self, command: str, **kwargs: Any) -> str:
            self.calls.append({"command": command, **kwargs})
            return "output"

    async def scenario() -> None:
        state = FakeState()
        result = await cli.send_command(as_state(state), command=None, path=".", timeout=2)

        assert result == "output"
        assert state.calls == [
            {
                "command": "echo 'Hello from iTerm2 API Wrapper!'",
                "path": str(Path(".").expanduser().resolve()),
                "broadcast": False,
                "timeout": 2.0,
            }
        ]

    asyncio.run(scenario())


def test_show_capabilities_collects_support_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        fake_capabilities = SimpleNamespace(
            supports_foo=lambda connection: True,
            supports_bar=lambda connection: False,
            unrelated=lambda connection: True,
        )
        import iterm2

        monkeypatch.setitem(sys.modules, "iterm2.capabilities", fake_capabilities)
        monkeypatch.setattr(iterm2, "capabilities", fake_capabilities, raising=False)
        monkeypatch.setattr(cli.log, "info", lambda *args, **kwargs: None)

        result = await cli.show_capabilities(as_state(SimpleNamespace(connection="connection")))

        assert result == {"supports_bar": False, "supports_foo": True}

    asyncio.run(scenario())


def test_alert_cli_helpers_delegate_to_alert_handlers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        state = as_state(
            SimpleNamespace(
            connection="connection", window=SimpleNamespace(window_id="window"), profile=SimpleNamespace(name="Default")
            )
        )

        async def fake_alert_handler(**kwargs: Any) -> int:
            return 1000

        async def fake_text_handler(**kwargs: Any) -> str:
            return "typed"

        async def fake_poly_handler(**kwargs: Any) -> dict[str, Any]:
            return {"button": "OK"}

        monkeypatch.setattr(cli, "alert_handler", fake_alert_handler)
        monkeypatch.setattr(cli, "text_input_alert_handler", fake_text_handler)
        monkeypatch.setattr(cli, "poly_modal_alert_handler", fake_poly_handler)
        monkeypatch.setattr(cli.log, "info", lambda *args, **kwargs: None)

        assert await cli.test_alerts(state) == 1000
        assert await cli.test_text_input_alert(state) == "typed"
        assert await cli.test_poly_modal_alert(state) == {"button": "OK"}
        assert await cli.test_all_alerts(state) == (1000, "typed", {"button": "OK"})

    asyncio.run(scenario())


def test_main_rejects_unknown_function(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli.log, "info", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli.log, "error", lambda *args, **kwargs: None)

    with pytest.raises(typer.Exit) as exc:
        cli.main("missing", [], new_tab=False, profile_name="Default", debug=False)

    assert exc.value.exit_code == 1


def test_main_dispatches_selected_function(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        loop = "loop"

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get_state(self) -> str:
            return "state"

    async def fake_send_command(state: str, command: str) -> str:
        return f"{state}:{command}"

    def fake_create_client(**kwargs: Any) -> FakeClient:
        calls.append(kwargs)
        return FakeClient()

    def fake_run_coro(coro: Any, event_loop: object) -> str:
        assert event_loop == "loop"
        try:
            coro.close()
        except AttributeError:
            pass
        return "output"

    monkeypatch.setattr(cli, "send_command", fake_send_command)
    monkeypatch.setattr(cli, "create_iterm_client", fake_create_client)
    monkeypatch.setattr(cli, "run_coro", fake_run_coro)
    monkeypatch.setattr(cli.log, "info", lambda *args, **kwargs: None)

    cli.main("send_command", ["echo hi"], new_tab=True, profile_name="Default", debug=True)

    assert calls == [{"timeout": None, "debug": True, "new_tab": True, "dedicated_profile_name": "Default"}]
