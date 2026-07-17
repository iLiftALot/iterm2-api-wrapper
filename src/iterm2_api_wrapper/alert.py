from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Any, Literal

from .api.it2alert import Alert, PolyModalAlert, TextInputAlert
from .api.it2app import async_get_app


if TYPE_CHECKING:
    from .api.it2app import App
    from .api.it2connection import Connection


async def alert_handler(
    connection: Connection, title: str, subtitle: str, window_id: str, button_names: list[str] | None = None
) -> int:
    """Shows the modal alert.

    :param connection: The connection to use.
    :type connection: :class:`Connection`
    :param title: The title of the alert.
    :type title: str
    :param subtitle: The subtitle of the alert.
    :type subtitle: str
    :param window_id: The :class:`~iterm2.Window` ID that the alert should appear in.
    :type window_id: str
    :param button_names: The names of the buttons.
    :type button_names: list[str] | None

    :returns:
        The index of the selected button, plus 1000.
        If no buttons were defined then a single button, "OK", is automatically added.
    :rtype: int

    :raises :class:`~iterm2.rpc.RPCException`: if the alert could not be shown.
    """

    alert_instance = Alert(title=title, subtitle=subtitle, window_id=window_id)
    for btn in button_names or []:
        alert_instance.add_button(btn)
    response = await alert_instance.async_run(connection)
    return response


async def text_input_alert_handler(
    connection: Connection,
    title: str,
    subtitle: str,
    placeholder: str,
    default_value: str,
    window_id: str | None = None,
) -> str | None:
    """Shows the modal alert.

    :param connection: The connection to use.
    :type connection: :class:`Connection`
    :param title: The title of the alert.
    :type title: str
    :param subtitle: The subtitle of the alert.
    :type subtitle: str
    :param placeholder: The placeholder for the text box.
    :type placeholder: str
    :param default_value: The default value of the text box.
    :type default_value: str
    :param window_id: The :class:`~iterm2.Window` ID that the alert should appear in.
    :type window_id: str | None

    :returns: The string entered, or None if the alert was canceled.
    :rtype: str | None

    :raises iterm2.rpc.RPCException: if something goes wrong.
    """

    alert_instance = TextInputAlert(
        title=title, subtitle=subtitle, placeholder=placeholder, default_value=default_value, window_id=window_id
    )
    response = await alert_instance.async_run(connection)
    return response


async def poly_modal_alert_handler(
    connection: Connection,
    title: str,
    subtitle: str,
    window_id: str | None = None,
    button_names: list[str] | None = None,
    checkboxes: list[tuple[str, Literal[0, 1]]] | None = None,
    combobox: tuple[list[str], str | None] | None = None,
    text_field: tuple[str, str] | None = None,
):
    """Shows the poly modal alert.

    :param connection: The connection to use.
    :type connection: :class:`Connection`
    :param title: The title of the alert.
    :type title: str
    :param subtitle: The subtitle of the alert.
    :type subtitle: str
    :param window_id: The :class:`~iterm2.Window` ID that the alert should appear in.
    :type window_id: str | None
    :param button_names: The names of the buttons.
    :type button_names: list[str] | None
    :param checkboxes: A list of tuples each containing the label and default value (0 or 1) of each checkbox.
    :type checkboxes: list[tuple[str, Literal[0, 1]]] | None
    :param combobox: A tuple containing the list of values and the default value for the combobox.
    :type combobox: tuple[list[str], str | None] | None
    :param text_field: A tuple containing a placeholder value and a default value.
    :type text_field: tuple[str, str] | None

    :returns:
        A :class:`~iterm2.alert.PolyModalResult` object containing values corresponding to the UI elements that were added:

        - The label of clicked button
        - Text entered into the field input
        - Selected combobox text ('' if combobox was present but nothing selected)
        - Array of checked checkbox labels.

        If no buttons were defined then a single button, "OK", is automatically added and "button"
        will be absent from PolyModalResult.
    :rtype: :class:`~iterm2.alert.PolyModalResult`

    :raises :class:`~iterm2.rpc.RPCException`: if something goes wrong.
    :raises ValueError: if the text field placeholders and default values are not the same length.
    """
    alert_instance = PolyModalAlert(title=title, subtitle=subtitle, window_id=window_id)

    for name in button_names or []:
        alert_instance.add_button(name)

    for cb_label, cb_default in checkboxes or []:
        alert_instance.add_checkbox_item(cb_label, cb_default)

    if combobox is not None:
        cb_items, cb_default = combobox
        combobox_caller = partial(alert_instance.add_combobox, items=cb_items)
        if cb_default is not None:
            combobox_caller.keywords["default"] = cb_default
        combobox_caller()

    if text_field is not None:
        placeholder, default_value = text_field
        alert_instance.add_text_field(placeholder, default_value)

    response = await alert_instance.async_run(connection=connection)
    return response


############################################################
# Example usage of the handlers
############################################################


"""
simple_alert = await alert_handler(
    title="iTerm2 Scripts",
    subtitle=(
        f"iTerm2 script is running in session {global_state.session.session_id} "
        f"in window {global_state.window.window_id}!"
    ),
    window_id=global_state.window.window_id,
    connection=global_state.connection,
)
text_input_alert = await text_input_alert_handler(
    title="Text Input Alert",
    subtitle="Please enter some text:",
    placeholder="Type here...",
    default_value="Default Text",
    connection=global_state.connection,
    window_id=global_state.window.window_id,
)
poly_modal_alert = await poly_modal_alert_handler(
    title="Poly Modal Alert",
    subtitle="This is a poly modal alert with multiple options.",
    connection=global_state.connection,
    window_id=global_state.window.window_id,
    button_names=["OK", "Cancel"],
    checkboxes=[("Option 1", 0), ("Option 2", 1)],
    combobox=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
    text_field=(("Field Placeholder", "Default Value")),
)
"""


############################################################
# Interactive Testing
############################################################


_app: App | None = None
_conn: Connection | None = None
run_until_complete: Any


async def main():
    global _conn, _app, run_until_complete
    from .api.it2connection import Connection, run_until_complete

    if _conn is None:
        _conn = await Connection.async_create()

        major_v, minor_v = _conn.iterm2_protocol_version
        print(f"\nConnection created with protocol version {major_v}.{minor_v}")

    if _app is None:
        _app = await async_get_app(_conn, True)

    print("Use the `run_until_complete` function.")


if __name__ == "__main__":
    asyncio.run(main())
