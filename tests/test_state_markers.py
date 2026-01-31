from __future__ import annotations

import base64
import re

from iterm2_api_wrapper.state import iTermState


def test_wrap_with_markers_generates_consistent_tokens() -> None:
    wrapped, begin, end_prefix = iTermState.wrap_with_markers("echo hello")

    assert begin.startswith("__PYTERM_MCP_BEGIN__")
    assert begin.endswith("__")

    token = begin.removeprefix("__PYTERM_MCP_BEGIN__").removesuffix("__")
    assert end_prefix == f"__PYTERM_MCP_END__{token}__"

    # The *printed* markers are contiguous, but the *typed* wrapper must not
    # contain them contiguously (to avoid false positives when scanning echoed
    # input lines).
    assert begin not in wrapped
    assert end_prefix not in wrapped


def test_wrap_with_markers_is_autopair_safe_and_round_trips_command() -> None:
    # Intentionally include characters that commonly trigger zsh autopair
    # widgets when typed interactively.
    command = "echo $(date) # comment (paren) 'quote'"

    wrapped, begin, end_prefix = iTermState.wrap_with_markers(command)

    # Autopair can corrupt injected keystrokes containing `(`; ensure the
    # wrapper itself contains no parentheses at all.
    assert "(" not in wrapped
    assert ")" not in wrapped

    # The raw command should not appear in the wrapper (it's base64-encoded).
    assert command not in wrapped

    # Extract the base64 payload and ensure we can reconstruct the original.
    m = re.search(r"`printf '%s' '(?P<b64>[^']*)' \| base64 -d`", wrapped)
    assert m is not None

    decoded = base64.b64decode(m.group("b64")).decode("utf-8")
    assert decoded == command

    # Sanity: marker components are present.
    assert "__PYTERM_MCP_BEGIN__" in wrapped
    assert "__PYTERM_MCP_END__" in wrapped
    assert begin.startswith("__PYTERM_MCP_BEGIN__")
    assert end_prefix.startswith("__PYTERM_MCP_END__")
