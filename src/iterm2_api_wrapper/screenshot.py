from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from zoneinfo import ZoneInfo

from iterm2_api_wrapper.api.it2window import maximum_visible_window_frame
from iterm2_api_wrapper.utils.logger import get_logger


if TYPE_CHECKING:
    from iterm2_api_wrapper.state import iTermState

logger = get_logger()


@dataclass(frozen=True, slots=True)
class _SessionMetadata:
    session_id: str
    session_name: str


@dataclass(frozen=True, slots=True, repr=False)
class ScreenshotResult:
    image_bytes: bytes
    path: Path
    session: _SessionMetadata

    type: Literal["image"] = "image"
    mime_type: Literal["image/png"] = "image/png"

    def __repr__(self) -> str:
        return (
            "ScreenshotResult(\n"
            f"    image_bytes={self.image_bytes[:10] + b'...' + self.image_bytes[-10:]},\n"
            f"    path={self.path},\n"
            f"    session={self.session},\n"
            f"    mime_type={self.mime_type}\n"
            ")"
        )

    @property
    def base64_data(self) -> str:
        return base64.b64encode(self.image_bytes).decode("ascii")

    @property
    def size(self) -> int:
        """Size of the PNG image in bytes."""
        return len(self.image_bytes)


def _get_timestamp() -> str:
    timestamp = datetime.now(tz=ZoneInfo("America/New_York")).strftime("%Y%m%d-%H%M%S")
    return timestamp


async def screenshot(state: iTermState) -> ScreenshotResult:
    session = state.session
    session_metadata = _SessionMetadata(session_id=session.session_id, session_name=session.name.strip())
    window = state.window

    original_frame = await window.async_get_frame()
    original_fullscreen = await window.async_get_fullscreen()
    maximum_frame = maximum_visible_window_frame(window)

    try:
        if original_fullscreen:
            await window.async_set_fullscreen(False)
            await asyncio.sleep(0.5)

        await window.async_set_frame(maximum_frame)
        await asyncio.sleep(0.5)

        logger.debug(
            "Expanded iTerm2 window to the display's visible frame:\n{}",
            {"window_size": maximum_frame.dict, "grid_size": session.grid_size},
        )

        screenshot_bytes = await session.async_screenshot()
        screenshot_path = Path.home() / "Downloads" / f"{session_metadata.session_name}_{_get_timestamp()}.png"
        screenshot_path.write_bytes(screenshot_bytes)
    finally:
        await window.async_set_frame(original_frame)

        if original_fullscreen:
            await window.async_set_fullscreen(True)

        logger.debug("Restored original window state")

    return ScreenshotResult(
        image_bytes=screenshot_bytes, path=screenshot_path, session=session_metadata, mime_type="image/png"
    )
