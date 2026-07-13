from __future__ import annotations

import runpy
from typing import Any

from pytest import MonkeyPatch

from iterm2_api_wrapper import cli as package_cli
from iterm2_api_wrapper import main as package_main


def test_init_delegates_to_run_until_complete(monkeypatch: MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run_until_complete(coro: object, retry: bool, **kwargs: Any) -> str:
        calls.append({"coro": coro, "retry": retry, "kwargs": kwargs})
        return "state"

    monkeypatch.setattr(package_main, "run_until_complete", fake_run_until_complete)

    result = package_main.init(retry=False, debug=True, new_tab=True)

    assert result == "state"
    assert calls == [
        {"coro": package_main.create_iterm_state, "retry": False, "kwargs": {"debug": True, "new_tab": True}}
    ]


def test_module_main_invokes_cli_app(monkeypatch: MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(package_cli, "app", lambda: calls.append("app"))

    runpy.run_module("iterm2_api_wrapper.__main__", run_name="__main__")

    assert calls == ["app"]
