from __future__ import annotations

from iterm2 import prompt
from typing_extensions import assert_type

from iterm2_api_wrapper.api.it2prompt import (
    CommandEndEvent,
    CommandEndEventWithId,
    PromptEvent,
    PromptEventWithId,
    PromptMonitor,
    PromptMonitorEvent,
    PromptMonitorEventWithId,
)


async def _check_prompt_monitor_contracts(monitor: PromptMonitor[None], include_id: bool) -> None:
    assert_type(await monitor.async_get(), PromptMonitorEvent)
    assert_type(await monitor.async_get(True), PromptMonitorEventWithId)
    assert_type(await monitor.async_get(include_id), PromptMonitorEvent | PromptMonitorEventWithId)
    assert_type(await monitor.async_get(mode=prompt.PromptMonitor.Mode.PROMPT), PromptEvent)
    assert_type(await monitor.async_get(True, mode=prompt.PromptMonitor.Mode.PROMPT), PromptEventWithId)
    assert_type(
        await monitor.async_get(include_id, mode=prompt.PromptMonitor.Mode.COMMAND_END),
        CommandEndEvent | CommandEndEventWithId,
    )

    upstream_monitor: prompt.PromptMonitor = monitor
    await upstream_monitor.async_get(include_id)
