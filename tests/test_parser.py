# ruff: noqa: RUF001
import asyncio
from typing import Any, cast

import pytest

from iterm2_api_wrapper.utils.parser import Parser

from .fake import SimpleNamespace, as_fake_session, make_state, patch_attr


def coord_range(start_x: int = 0, start_y: int = 0, end_x: int = 0, end_y: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        start=SimpleNamespace(x=start_x, y=start_y),
        end=SimpleNamespace(x=end_x, y=end_y),
        proto=f"{start_x},{start_y}:{end_x},{end_y}",
    )


def prompt_stub(
    *,
    output_range: SimpleNamespace | None = None,
    command_range: SimpleNamespace | None = None,
    prompt_range: SimpleNamespace | None = None,
    command: str | None = "echo hi",
) -> SimpleNamespace:
    return SimpleNamespace(
        output_range=output_range or coord_range(),
        command_range=command_range or coord_range(),
        prompt_range=prompt_range or coord_range(),
        command=command,
        excluded_subranges=[],
    )


async def no_current_prompt(unique_id: str | None = None) -> None:
    del unique_id
    return None


def test_parser_requires_extraction_before_result_properties_and_diff() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        parser = Parser(state, cast(Any, prompt_stub()), "echo hi")

        with pytest.raises(RuntimeError, match="output hasn't been extracted"):
            _ = parser.output
        with pytest.raises(RuntimeError, match="prompt hasn't been extracted"):
            _ = parser.prompt
        with pytest.raises(RuntimeError, match="command text hasn't been extracted"):
            _ = parser.command_parsed
        with pytest.raises(RuntimeError, match="initial_snapshot was not passed"):
            await parser.diff()

    asyncio.run(scenario())


def test_parser_read_helpers_extract_and_cache_prompt_and_command() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        parsed_prompt = prompt_stub(
            prompt_range=coord_range(start_y=0, end_y=1),
            command_range=coord_range(start_y=1, end_y=2),
            command=None,
        )
        as_fake_session(state.session).contents = [
            SimpleNamespace(string="prompt$", hard_eol=True),
            SimpleNamespace(string="echo hi", hard_eol=True),
        ]
        parser = Parser(state, cast(Any, parsed_prompt), "echo hi")

        assert await parser.read_prompt() == "prompt$"
        assert await parser.read_command_text() == "echo hi"
        assert await parser.read_prompt_lines() == ["prompt$"]
        assert parser.prompt == "prompt$"
        assert parser.command_parsed == "echo hi"
        assert parser.command_expected is True

    asyncio.run(scenario())


def test_parser_reads_partial_first_and_last_rows() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        patch_attr(state, "_get_prompt", no_current_prompt)
        parsed_prompt = prompt_stub(output_range=coord_range(start_x=2, start_y=0, end_x=3, end_y=1))
        as_fake_session(state.session).contents = [
            SimpleNamespace(string="xxhello", hard_eol=True),
            SimpleNamespace(string="byezzz", hard_eol=True),
        ]

        parser = Parser(state, cast(Any, parsed_prompt), "echo hi")

        assert await parser.read_output() == "hello\nbye"

    asyncio.run(scenario())


def test_prompt_marker_lines_handles_missing_or_blank_command() -> None:
    prompt_text = "line one\nline two"

    assert Parser.prompt_marker_lines(prompt_text, None) == ["line one", "line two"]
    assert Parser.prompt_marker_lines(prompt_text, "  \n") == ["line one", "line two"]


def test_parser_preserves_soft_wraps() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        patch_attr(state, "_get_prompt", no_current_prompt)
        prompt = prompt_stub(output_range=coord_range(end_y=2), command="echo hi")
        session = as_fake_session(state.session)
        session.contents = [
            SimpleNamespace(string="soft-", hard_eol=False),
            SimpleNamespace(string="wrapped", hard_eol=True),
        ]

        parser = Parser(state, cast(Any, prompt), "echo hi")
        assert await parser.read_output() == "soft-wrapped"

    asyncio.run(scenario())


def test_parser_clips_output_range_before_current_prompt() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        command_prompt = prompt_stub(
            output_range=coord_range(start_y=0, end_x=2, end_y=4),
            command="command brew doctor",
        )
        current_prompt = prompt_stub(
            prompt_range=coord_range(start_y=2, end_x=2, end_y=4),
            command="",
        )

        async def get_prompt(unique_id: str | None = None) -> Any:
            del unique_id
            return current_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        session = as_fake_session(state.session)
        session.contents = [
            SimpleNamespace(string="Your system is ready to brew.", hard_eol=True),
            SimpleNamespace(string="", hard_eol=True),
            SimpleNamespace(string="~/CodeProjects/project master* 13:35:23", hard_eol=True),
            SimpleNamespace(string="❯ ", hard_eol=False),
        ]

        parser = Parser(state, cast(Any, command_prompt), "command brew doctor")
        await parser.parse()

        assert parser.output == "Your system is ready to brew."

    asyncio.run(scenario())


def test_parser_does_not_clip_when_current_prompt_is_outside_output_range() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        command_prompt = prompt_stub(output_range=coord_range(end_y=1), command="echo hi")
        current_prompt = prompt_stub(prompt_range=coord_range(start_y=5, end_x=2, end_y=6), command="")

        async def get_prompt(unique_id: str | None = None) -> Any:
            del unique_id
            return current_prompt

        patch_attr(state, "_get_prompt", get_prompt)
        as_fake_session(state.session).contents = [SimpleNamespace(string="hi", hard_eol=True)]

        parser = Parser(state, cast(Any, command_prompt), "echo hi")
        await parser.parse()

        assert parser.output == "hi"

    asyncio.run(scenario())


def test_parser_falls_back_to_snapshot_diff_when_command_does_not_match() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        command_prompt = prompt_stub(
            output_range=coord_range(end_y=1),
            prompt_range=coord_range(end_x=7),
            command_range=coord_range(),
            command="stale command",
        )
        current_prompt = prompt_stub(prompt_range=coord_range(end_x=7), command="")
        snapshots = iter([["prompt$"], ["prompt$", "echo hi", "fallback", "prompt$"]])

        async def snapshot(*, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
            del trim_end, filter_all_empty
            return next(snapshots)

        async def get_prompt(unique_id: str | None = None) -> Any:
            del unique_id
            return current_prompt

        patch_attr(state, "_snapshot", snapshot)
        patch_attr(state, "_get_prompt", get_prompt)
        as_fake_session(state.session).contents = [SimpleNamespace(string="prompt$", hard_eol=True)]

        initial_snapshot = await state._snapshot()
        parser = Parser(state, cast(Any, command_prompt), "echo hi", initial_snapshot=initial_snapshot)
        await parser.parse()

        assert parser.output == "fallback"

    asyncio.run(scenario())


def test_parser_diff_edge_cases() -> None:
    async def scenario() -> None:
        state = make_state(asyncio.get_running_loop())
        prompt = prompt_stub(command="echo hi")

        async def unchanged_snapshot(*, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
            del trim_end, filter_all_empty
            return ["a", "b"]

        patch_attr(state, "_snapshot", unchanged_snapshot)
        assert await Parser(state, cast(Any, prompt), "echo hi", initial_snapshot=["a", "b"]).diff() == []

        async def append_snapshot(*, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
            del trim_end, filter_all_empty
            return ["a", "b", "c"]

        patch_attr(state, "_snapshot", append_snapshot)
        assert await Parser(state, cast(Any, prompt), "echo hi", initial_snapshot=["a"]).diff() == ["b", "c"]

        async def sandwich_snapshot(*, trim_end: bool = True, filter_all_empty: bool = False) -> list[str]:
            del trim_end, filter_all_empty
            return ["p", "y", "z", "q"]

        patch_attr(state, "_snapshot", sandwich_snapshot)
        assert await Parser(state, cast(Any, prompt), "echo hi", initial_snapshot=["p", "x", "q"]).diff() == [
            "y",
            "z",
        ]

    asyncio.run(scenario())


def test_parser_prompt_marker_lines_removes_wrapped_command_text() -> None:
    prompt_text = "\n".join(
        [
            "~ master* 1m 27s",
            "14:44:51",
            "❯ brew install python-tk@3.13",
            "brew install python-gdbm@3.13",
            "br",
        ]
    )
    command = "\n".join(
        [
            "brew install python-tk@3.13",
            "brew install python-gdbm@3.13",
            "brew install node",
        ]
    )

    assert Parser.prompt_marker_lines(prompt_text, command) == ["~ master* 1m 27s", "14:44:51", "❯"]
