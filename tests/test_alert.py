from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from iterm2_api_wrapper import alert as alert_module


if TYPE_CHECKING:
    from iterm2_api_wrapper.api.it2connection import Connection
else:
    Connection = object


def as_connection(connection: object) -> Connection:
    return cast(Connection, connection)


class FakeAlert:
    instances: ClassVar[list[FakeAlert]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.buttons: list[str] = []
        self.run_args: tuple[Any, ...] = ()
        self.run_kwargs: dict[str, Any] = {}
        FakeAlert.instances.append(self)

    def add_button(self, name: str) -> None:
        self.buttons.append(name)

    async def async_run(self, *args: Any, **kwargs: Any) -> Any:
        self.run_args = args
        self.run_kwargs = kwargs
        return "alert-result"


class FakeTextInputAlert(FakeAlert):
    async def async_run(self, *args: Any, **kwargs: Any) -> str:
        self.run_args = args
        self.run_kwargs = kwargs
        return "typed-value"


class FakePolyModalAlert(FakeAlert):
    poly_instances: ClassVar[list[FakePolyModalAlert]] = []

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.checkboxes: list[tuple[str, int]] = []
        self.comboboxes: list[dict[str, Any]] = []
        self.text_fields: list[tuple[str, str]] = []
        FakePolyModalAlert.poly_instances.append(self)

    def add_checkbox_item(self, label: str, default: int) -> None:
        self.checkboxes.append((label, default))

    def add_combobox(self, **kwargs: Any) -> None:
        self.comboboxes.append(kwargs)

    def add_text_field(self, placeholder: str, default_value: str) -> None:
        self.text_fields.append((placeholder, default_value))

    async def async_run(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.run_args = args
        self.run_kwargs = kwargs
        return {"button": "OK"}


def test_alert_handler_wires_buttons_and_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAlert.instances.clear()
    monkeypatch.setattr(alert_module, "Alert", FakeAlert)

    result = asyncio.run(
        alert_module.alert_handler(
            title="Title",
            subtitle="Subtitle",
            window_id="window-1",
            connection=as_connection("connection"),
            button_names=["OK", "Cancel"],
        )
    )

    instance = FakeAlert.instances[-1]
    assert result == "alert-result"
    assert instance.kwargs == {"title": "Title", "subtitle": "Subtitle", "window_id": "window-1"}
    assert instance.buttons == ["OK", "Cancel"]
    assert instance.run_args == ("connection",)


def test_text_input_alert_handler_wires_constructor(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAlert.instances.clear()
    monkeypatch.setattr(alert_module, "TextInputAlert", FakeTextInputAlert)

    result = asyncio.run(
        alert_module.text_input_alert_handler(
            title="Title",
            subtitle="Subtitle",
            placeholder="Name",
            default_value="Alice",
            connection=as_connection("connection"),
            window_id="window-1",
        )
    )

    instance = FakeAlert.instances[-1]
    assert result == "typed-value"
    assert instance.kwargs == {
        "title": "Title",
        "subtitle": "Subtitle",
        "placeholder": "Name",
        "default_value": "Alice",
        "window_id": "window-1",
    }
    assert instance.run_args == ("connection",)


def test_poly_modal_alert_handler_wires_all_optional_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeAlert.instances.clear()
    FakePolyModalAlert.poly_instances.clear()
    monkeypatch.setattr(alert_module, "PolyModalAlert", FakePolyModalAlert)

    result = asyncio.run(
        alert_module.poly_modal_alert_handler(
            title="Title",
            subtitle="Subtitle",
            connection=as_connection("connection"),
            window_id="window-1",
            button_names=["OK"],
            checkboxes=[("Remember", 1)],
            comboboxes=(["One", "Two"], "Two"),
            text_fields=(["First", "Last"], ["Ada", "Lovelace"]),
        )
    )

    instance = FakePolyModalAlert.poly_instances[-1]
    assert result == {"button": "OK"}
    assert instance.buttons == ["OK"]
    assert instance.checkboxes == [("Remember", 1)]
    assert instance.comboboxes == [{"items": ["One", "Two"], "default": "Two"}]
    assert instance.text_fields == [("First", "Ada"), ("Last", "Lovelace")]
    assert instance.run_kwargs == {"connection": "connection"}


def test_poly_modal_alert_handler_combobox_without_default(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePolyModalAlert.poly_instances.clear()
    monkeypatch.setattr(alert_module, "PolyModalAlert", FakePolyModalAlert)

    result = asyncio.run(
        alert_module.poly_modal_alert_handler(
            title="Title", subtitle="Subtitle", connection=as_connection("connection"), comboboxes=(["A", "B"], None)
        )
    )

    instance = FakePolyModalAlert.poly_instances[-1]
    assert result == {"button": "OK"}
    # No default supplied -> only items are passed to add_combobox.
    assert instance.comboboxes == [{"items": ["A", "B"]}]
    assert instance.checkboxes == []
    assert instance.text_fields == []


def test_poly_modal_alert_handler_without_optional_controls(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePolyModalAlert.poly_instances.clear()
    monkeypatch.setattr(alert_module, "PolyModalAlert", FakePolyModalAlert)

    result = asyncio.run(
        alert_module.poly_modal_alert_handler(
            title="Title", subtitle="Subtitle", connection=as_connection("connection")
        )
    )

    instance = FakePolyModalAlert.poly_instances[-1]
    assert result == {"button": "OK"}
    assert instance.buttons == []
    assert instance.comboboxes == []
    assert instance.checkboxes == []
    assert instance.text_fields == []


def test_poly_modal_alert_handler_rejects_mismatched_text_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePolyModalAlert.poly_instances.clear()
    monkeypatch.setattr(alert_module, "PolyModalAlert", FakePolyModalAlert)

    with pytest.raises(ValueError):
        asyncio.run(
            alert_module.poly_modal_alert_handler(
                title="Title",
                subtitle="Subtitle",
                connection=as_connection("connection"),
                text_fields=(["Only one"], ["one", "two"]),
            )
        )
