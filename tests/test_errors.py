from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from iterm2_api_wrapper.errors import (
    ProfileNotFoundError,
    SessionNotFoundError,
    TabNotFoundError,
    WindowNotFoundError,
    iTermError,
)


def _note_text(exc: BaseException) -> str:
    return "\n".join(getattr(exc, "__notes__", []))


def test_iterm_error_uses_class_name_as_default_message_and_module() -> None:
    class CustomError(iTermError):
        pass

    exc = CustomError()

    assert CustomError.msg == "CustomError"
    assert exc.__module__ == "CustomError"
    assert "CustomError" in _note_text(exc)


def test_iterm_error_formats_message_with_kwargs() -> None:
    class GreetingError(iTermError):
        msg = "Hello {name}"

    exc = GreetingError(name="Ada")

    assert "Hello Ada" in _note_text(exc)


def test_profile_not_found_error_lists_available_profiles() -> None:
    profiles = {
        "Default": cast("object", SimpleNamespace(guid="GUID-1")),
        "Dev": cast("object", SimpleNamespace(guid="GUID-2")),
    }

    with pytest.raises(ProfileNotFoundError) as exc_info:
        raise ProfileNotFoundError(target_profile_name="Missing", profile_data=cast(dict, profiles))

    note = _note_text(exc_info.value)
    assert "Missing" in note
    # Names are padded so GUIDs align to the longest name + 1.
    assert "- Default GUID-1" in note
    assert "- Dev     GUID-2" in note


def test_window_tab_session_errors_embed_profile_name() -> None:
    assert "my-profile" in _note_text(WindowNotFoundError("my-profile"))
    assert "my-profile" in _note_text(TabNotFoundError("my-profile"))
    assert "session-guid" in _note_text(SessionNotFoundError("session-guid"))


def test_iterm_errors_are_raisable_base_exceptions() -> None:
    for error_cls, args in ((WindowNotFoundError, ("p",)), (TabNotFoundError, ("p",)), (SessionNotFoundError, ("p",))):
        with pytest.raises(error_cls):
            raise error_cls(*args)
