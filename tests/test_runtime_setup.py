from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from iterm2.capabilities import AppVersionTooOld

from iterm2_api_wrapper import runtime_setup as it2runtime


def connection(version: tuple[int, int] = (1, 14)) -> Any:
    return SimpleNamespace(iterm2_protocol_version=version)


def test_validate_runtime_checks_every_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, object]] = []

    monkeypatch.setattr(
        it2runtime,
        "check_supports_prompt_monitor_modes",
        lambda conn: calls.append(("prompt", conn)),
    )
    monkeypatch.setattr(
        it2runtime,
        "check_supports_get_default_profile",
        lambda conn: calls.append(("profile", conn)),
    )
    monkeypatch.setattr(
        it2runtime,
        "check_supports_prompt_id",
        lambda conn: calls.append(("prompt_id", conn)),
    )

    first = connection()
    second = connection()

    it2runtime.validate_iterm2_runtime(first)
    it2runtime.validate_iterm2_runtime(second)

    assert calls == [
        ("prompt", first),
        ("profile", first),
        ("prompt_id", first),
        ("prompt", second),
        ("profile", second),
        ("prompt_id", second),
    ]


def test_validate_runtime_rejects_unsupported_connection() -> None:
    with pytest.raises(AppVersionTooOld):
        it2runtime.validate_iterm2_runtime(connection((1, 4)))


def test_validate_runtime_logs_protocol_version(monkeypatch: pytest.MonkeyPatch) -> None:
    logged: list[str] = []

    monkeypatch.setattr(it2runtime.log, "debug", lambda message: logged.append(message))

    it2runtime.validate_iterm2_runtime(connection((1, 14)))

    assert logged == ["iTerm protocol version 1.14"]
