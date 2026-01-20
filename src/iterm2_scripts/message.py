from functools import partial
from typing import Literal

from iterm2 import alert, connection, session


async def send_command_to_iterm(session: session.Session, command: str) -> None:
    """Send a command to the iTerm2 session."""
    await session.async_send_text(command + "\n", suppress_broadcast=True)


async def alert_handler(
    title: str,
    subtitle: str,
    window_id: str,
    connection: connection.Connection,
    button_names: list[str] | None = None,
) -> int:
    """Shows the modal alert.

    :param connection: The connection to use.
    :returns: The index of the selected button, plus 1000. If no buttons
    were defined
        then a single button, "OK", is automatically added.

    :raises iterm2.rpc.RPCException: if the alert could not be shown.
    """

    alert_instance = alert.Alert(title=title, subtitle=subtitle, window_id=window_id)
    for btn in button_names or []:
        alert_instance.add_button(btn)
    response = await alert_instance.async_run(connection)
    return response


async def text_input_alert_handler(
    title: str,
    subtitle: str,
    placeholder: str,
    default_value: str,
    connection: connection.Connection,
    window_id: str | None = None,
):
    """Shows the modal alert.

    :param connection: The connection to use.
    :returns: The string entered, or None if the alert was canceled.

    :raises iterm2.rpc.RPCException: if something goes wrong.
    """

    alert_instance = alert.TextInputAlert(
        title=title,
        subtitle=subtitle,
        placeholder=placeholder,
        default_value=default_value,
        window_id=window_id,
    )
    response = await alert_instance.async_run(connection)
    return response


async def poly_modal_alert_handler(
    title: str,
    subtitle: str,
    connection: connection.Connection,
    window_id: str | None = None,
    button_names: list[str] | None = None,
    checkboxes: list[tuple[str, Literal[0, 1]]] | None = None,
    comboboxes: tuple[list[str], str | None] | None = None,
    text_fields: tuple[list[str], list[str]] | None = None,
):
    """Shows the poly modal alert.

    :param connection: The connection to use.
    :returns: A PolyModalResult object containing values corresponding to
    the UI elements that were added
        - the label of clicked button
        - text entered into the field input
        - selected combobox text ('' if combobox was present but nothing
        selected)
        - array of checked checkbox labels.
    If no buttons were defined
        then a single button, "OK", is automatically added
            and "button" will be absent from PolyModalResult.

    :raises iterm2.rpc.RPCException: if something goes wrong.
    """

    alert_instance = alert.PolyModalAlert(
        title=title, subtitle=subtitle, window_id=window_id
    )

    for btn in button_names or []:
        alert_instance.add_button(btn)

    for cb_label, cb_default in checkboxes or []:
        alert_instance.add_checkbox_item(cb_label, cb_default)

    if comboboxes is not None:
        combobox_caller = partial(alert_instance.add_combobox, items=comboboxes[0])
        if comboboxes[1] is not None:
            combobox_caller.keywords["default"] = comboboxes[1]
        combobox_caller()

    if text_fields is not None:
        placeholders, default_values = text_fields
        for placeholder, default_value in zip(placeholders, default_values, strict=True):
            alert_instance.add_text_field(placeholder, default_value)

    response = await alert_instance.async_run(connection=connection)
    return response


############################################################
# Example usage of the handlers
############################################################


"""
simple_alert = await alert_handler(
    title="iTerm2 Scripts",
    subtitle=f"iTerm2 script is running in session {global_state.session.session_id} in window {global_state.window.window_id}!",
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
    comboboxes=(["Choice 1", "Choice 2", "Choice 3"], "Choice 2"),
    text_fields=(
        ["Field 1", "Field 2", "Field 3"],
        ["Default Value 1", "Default Value 2", "Default Value 3"],
    ),
)
"""
