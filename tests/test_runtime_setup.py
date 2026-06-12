from __future__ import annotations

from types import SimpleNamespace

from iterm2_api_wrapper.api import it2runtime


def test_validate_app_version_checks_capabilities(monkeypatch) -> None:
    calls: list[str] = []
    connection = SimpleNamespace(iterm2_protocol_version=(1, 14))

    monkeypatch.setattr(it2runtime, "check_supports_prompt_monitor_modes", lambda conn: calls.append("prompt"))
    monkeypatch.setattr(it2runtime, "check_supports_get_default_profile", lambda conn: calls.append("profile"))
    monkeypatch.setattr(it2runtime, "check_supports_prompt_id", lambda conn: calls.append("prompt_id"))

    it2runtime._validate_app_version(connection)  # pyright: ignore[reportArgumentType]

    assert calls == ["prompt", "profile", "prompt_id"]


def test_bootstrap_and_validate_runtime_can_be_called_sequentially(monkeypatch) -> None:
    calls: list[object] = []

    monkeypatch.setattr(it2runtime, "bootstrap_iterm2_runtime", lambda: calls.append("bootstrap"))
    monkeypatch.setattr(
        it2runtime, "validate_iterm2_runtime", lambda connection: calls.append(("validate", connection))
    )

    bootstrap = it2runtime.bootstrap_iterm2_runtime()
    validate = it2runtime.validate_iterm2_runtime("connection")  # pyright: ignore[reportArgumentType]

    assert bootstrap is None
    assert validate is None
    assert calls == ["bootstrap", ("validate", "connection")]
