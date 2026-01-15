from typing import Literal
import iterm2
import iterm2.alert
from functools import partial


async def alert_handler(
    title: str,
    subtitle: str,
    windowId: str,
    connection: iterm2.Connection,
    button_names: list[str] | None = None,
) -> int:
    """Handle alert notification."""

    alert = iterm2.alert.Alert(title=title, subtitle=subtitle, window_id=windowId)
    for btn in button_names or []:
        alert.add_button(btn)
    response = await alert.async_run(connection)
    return response


async def text_input_alert_handler(
    title: str,
    subtitle: str,
    placeholder: str,
    default_value: str,
    connection: iterm2.Connection,
    window_id: str | None = None,
):
    """Handle text input alert notification."""

    alert = iterm2.alert.TextInputAlert(
        title=title,
        subtitle=subtitle,
        placeholder=placeholder,
        default_value=default_value,
        window_id=window_id,
    )
    response = await alert.async_run(connection)
    return response


async def poly_modal_alert_handler(
    title: str,
    subtitle: str,
    connection: iterm2.Connection,
    window_id: str | None = None,
    button_names: list[str] | None = None,
    checkboxes: list[tuple[str, Literal[0, 1]]] | None = None,
    comboboxes: tuple[list[str], str | None] | None = None,
    text_fields: tuple[list[str], list[str]] | None = None,
):
    """Handle poly modal alert notification."""

    alert = iterm2.alert.PolyModalAlert(
        title=title, subtitle=subtitle, window_id=window_id
    )

    for btn in button_names or []:
        alert.add_button(btn)

    for cb_label, cb_default in checkboxes or []:
        alert.add_checkbox_item(cb_label, cb_default)

    if comboboxes is not None:
        combobox_caller = partial(alert.add_combobox, items=comboboxes[0])
        if comboboxes[1] is not None:
            combobox_caller.keywords["default"] = comboboxes[1]
        combobox_caller()

    if text_fields is not None:
        placeholders, default_values = text_fields
        for placeholder, default_value in zip(placeholders, default_values, strict=True):
            alert.add_text_field(placeholder, default_value)

    response = await alert.async_run(connection=connection)
    return response


############################################################
# Example usage of the handlers
############################################################


"""
simple_alert = await alert_handler(
    title="iTerm2 Scripts",
    subtitle=f"iTerm2 script is running in session {global_state.session.session_id} in window {global_state.window.window_id}!",
    windowId=global_state.window.window_id,
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
