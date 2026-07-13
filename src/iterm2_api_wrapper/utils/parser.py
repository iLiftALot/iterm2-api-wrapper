from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .._logging import PrettyLog
from ..api.it2measurement import CoordRange
from ..api.it2transaction import Transaction


if TYPE_CHECKING:
    from ..api.it2connection import Connection
    from ..api.it2prompt import Prompt
    from ..api.it2session import Session
    from ..state import iTermState


log = PrettyLog.get_logger(__name__)


@dataclass
class ParseResult:
    output: str
    prompt: str
    command: str | None
    command_parsed: str


class Parser:
    """Prompt, command, and output text extraction for an iTerm2 command lifecycle.

    `Parser` owns coordinate-range reading and cleanup logic. :class:`iTermState`
    should use it for extracting output/prompt text instead of directly reading
    screen ranges.
    """

    def __init__(
        self, state: iTermState, prompt: Prompt, expected_command: str, initial_snapshot: list[str] | None = None
    ) -> None:
        self._state = state
        self._prompt_obj = prompt
        self._expected_command = expected_command
        self._initial_snapshot = initial_snapshot
        self._connection: Connection = state.connection
        self._session: Session = state.session

        # Wrap defensively. When prompts come from this package's async_get_*
        # helpers these are already CoordRange instances, but PromptMonitor
        # prompt events may still be upstream iTerm2 Prompt objects.
        self._output_range = CoordRange(prompt.output_range)
        self._prompt_range = CoordRange(prompt.prompt_range)
        self._command_range = CoordRange(prompt.command_range)

        self._output: str | None = None
        self._prompt: str | None = None
        self._command: str | None = prompt.command
        self._command_parsed: str | None = None

    async def __aenter__(self) -> Parser:
        await self.parse()
        return self

    async def __aexit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return

    @property
    def result(self) -> ParseResult:
        return ParseResult(self.output, self.prompt, self.command, self.command_parsed)

    @property
    def output(self) -> str:
        """Command output text excluding prompt and command text."""
        if self._output is None:
            raise RuntimeError("The output hasn't been extracted yet.")
        return self._output

    @property
    def prompt(self) -> str:
        """Prompt text, sanitized separately via `prompt_lines` when needed."""
        if self._prompt is None:
            raise RuntimeError("The prompt hasn't been extracted yet.")
        return self._prompt

    @property
    def command(self) -> str | None:
        """The command reported by iTerm2 shell integration."""
        return self._command

    @property
    def command_parsed(self) -> str:
        """Raw command-range text read from the terminal screen."""
        if self._command_parsed is None:
            raise RuntimeError("The command text hasn't been extracted yet.")
        return self._command_parsed

    @property
    def command_expected(self) -> bool:
        """Determine if the current command matches the designated expected command."""
        default_cmd_expected = (self.command or "").strip() == self._expected_command.strip()
        parsed_cmd_expected = self.command_parsed.strip() == self._expected_command.strip()
        return bool(default_cmd_expected or parsed_cmd_expected)

    @property
    def prompt_lines(self) -> list[str]:
        """Return prompt marker lines, removing command text if prompt_range overlaps the command."""
        command = self.command or (self._command_parsed or "")
        return self.prompt_marker_lines(self.prompt, command)

    async def parse(self) -> Parser:
        """Read prompt, command-range text, and output text."""
        output_range = await self._output_range_clipped_before_current_prompt()

        async with Transaction(self._connection):
            self._output = await self._read_coord_range(output_range)
            self._prompt = await self._read_coord_range(self._prompt_range)
            self._command_parsed = await self._read_coord_range(self._command_range)

        if not self.command_expected:
            self._output = await self._output_fallback()

        self._output = self._output.rstrip("\n")

        return self

    async def read_output(self) -> str:
        """Read only the command output range."""
        if self._output is None:
            output_range = await self._output_range_clipped_before_current_prompt()

            async with Transaction(self._connection):
                self._output = await self._read_coord_range(output_range)

            self._output = self._output.rstrip("\n")

        return self._output

    async def read_prompt(self) -> str:
        """Read only the prompt range."""
        if self._prompt is None:
            async with Transaction(self._connection):
                self._prompt = await self._read_coord_range(self._prompt_range)
        return self._prompt

    async def read_command_text(self) -> str:
        """Read only the command range text."""
        if self._command_parsed is None:
            async with Transaction(self._connection):
                self._command_parsed = await self._read_coord_range(self._command_range)
        return self._command_parsed

    async def read_prompt_lines(self) -> list[str]:
        """Read prompt marker lines with overlapping command text removed."""
        await self.read_prompt()  # Ensure self._prompt is not None
        if not self.command and self._command_parsed is None:
            await self.read_command_text()
        return self.prompt_lines

    async def diff(self) -> list[str]:
        """Return the changed block between two terminal snapshots."""
        if self._initial_snapshot is None:
            raise RuntimeError("Parser.initial_snapshot was not passed during initialization.")

        before = self._initial_snapshot
        after = await self._state._snapshot()
        prefix = 0
        max_prefix = min(len(before), len(after))
        while prefix < max_prefix and before[prefix] == after[prefix]:
            prefix += 1

        suffix = 0
        max_suffix = min(len(before) - prefix, len(after) - prefix)
        while suffix < max_suffix and before[-(suffix + 1)] == after[-(suffix + 1)]:
            suffix += 1

        end = len(after) - suffix if suffix else len(after)
        return after[prefix:end]

    async def _output_fallback(self) -> str:
        """Remove echoed command text and freshly drawn prompt lines from snapshot-diff fallback output."""
        lines = await self.diff()
        prompt_lines = await self._current_prompt_lines_for_fallback()
        command = self._expected_command
        cleaned = list(lines)
        markers = {marker.rstrip() for marker in prompt_lines if marker.strip()}

        while cleaned and cleaned[-1].rstrip() in markers:
            cleaned.pop()

        removed_echo = False
        if needle := command.strip():
            first_command_line = next((line.strip() for line in needle.splitlines() if line.strip()), needle)
            for index, line in enumerate(cleaned):
                if needle in line or first_command_line in line:
                    del cleaned[: index + 1]
                    removed_echo = True
                    break

        if removed_echo:
            command_fragments = [line.strip() for line in command.splitlines()[1:] if line.strip()]
            while cleaned and any(fragment in cleaned[0] for fragment in command_fragments):
                cleaned.pop(0)

        while cleaned and cleaned[0].rstrip() in markers:
            cleaned.pop(0)

        return "\n".join(cleaned)

    async def _current_prompt_lines_for_fallback(self) -> list[str]:
        """Return current prompt marker lines for snapshot-diff fallback cleanup."""
        current_prompt = await self._state._get_prompt()
        if current_prompt is None:
            return self.prompt_lines

        current_prompt_range = CoordRange(current_prompt.prompt_range)

        async with Transaction(self._connection):
            prompt_text = await self._read_coord_range(current_prompt_range)

        command = current_prompt.command or self._expected_command
        return self.prompt_marker_lines(prompt_text, command)

    async def _read_coord_range(self, coord_range: CoordRange) -> str:
        """Read an iTerm2 coordinate range, slicing only the first and last rows by x offsets."""
        if coord_range.is_inverted or coord_range.is_empty:
            return ""

        start, end = coord_range.start, coord_range.end
        contents = await self._session.async_get_contents(start.y, coord_range.total_lines)
        lines = [(line.string, bool(getattr(line, "hard_eol", True))) for line in contents]
        if not lines:
            return ""

        if end.x > 0:
            last_text, _ = lines[-1]
            lines[-1] = (last_text[: end.x], False)

        first_text, first_hard_eol = lines[0]
        lines[0] = (first_text[start.x :], first_hard_eol)

        return self.join_screen_lines(lines)

    async def _latest_prompt_range(self) -> CoordRange | None:
        """Return the current/latest prompt range, if available."""
        current_prompt = await self._state._get_prompt()
        if current_prompt is None:
            return None

        return CoordRange(current_prompt.prompt_range)

    async def _output_range_clipped_before_current_prompt(self) -> CoordRange:
        """Clip output_range before the freshly drawn prompt when iTerm2 includes it."""
        current_prompt_range = await self._latest_prompt_range()
        if current_prompt_range is None:
            return self._output_range

        clipped_output_range = self._output_range.clipped_before(current_prompt_range.start)

        if clipped_output_range is not self._output_range:
            log.debug(
                "Clipped command output range before current prompt",
                {
                    "original_output_start": self._output_range.start,
                    "original_output_end": self._output_range.end,
                    "current_prompt_start": current_prompt_range.start,
                    "current_prompt_end": current_prompt_range.end,
                    "clipped_output_start": clipped_output_range.start,
                    "clipped_output_end": clipped_output_range.end,
                },
            )

        return clipped_output_range

    @staticmethod
    def join_screen_lines(lines: list[tuple[str, bool]]) -> str:
        """Join terminal screen rows while preserving soft wraps.

        iTerm2 returns physical screen rows. Rows with ``hard_eol=False`` are soft
        wraps and should be concatenated without an inserted newline.
        """
        parts: list[str] = []
        last_index = len(lines) - 1

        for index, (text, hard_eol) in enumerate(lines):
            parts.append(text)
            if hard_eol and index != last_index:
                parts.append("\n")

        return "".join(parts)

    @staticmethod
    def prompt_marker_lines(prompt_text: str, command: str | None = None) -> list[str]:
        """Return prompt marker lines, removing command text if prompt_range overlaps the command."""
        log.add_context(prompt_marker_lines_ctx="Extracting prompt marker lines")
        log.debug("Parsing for prompt marker lines:", {"prompt_text": prompt_text, "command": command})
        lines = prompt_text.splitlines()
        if command is None:
            log.debug("Command was passed as None; Returning lines as is...", lines)
            return lines

        command_lines = [line.strip() for line in command.splitlines() if line.strip()]
        if not command_lines:
            log.debug("No command lines were parsed from the provided command...")
            return lines

        first_command_line = command_lines[0]
        for index, line in enumerate(lines):
            if first_command_line in line:
                prefix = line.split(first_command_line, 1)[0].rstrip()
                lines = [*lines[:index], *([prefix] if prefix else [])]
                log.debug(
                    "Found the line containing the first command line.",
                    {"first_command_line": first_command_line, "prefix": prefix},
                )
                break

        log.debug("Returning prompt marker lines:", lines)
        log.remove_context("prompt_marker_lines_ctx")
        return lines
