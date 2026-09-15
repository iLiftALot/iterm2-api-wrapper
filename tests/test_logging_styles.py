from __future__ import annotations

from types import MappingProxyType
from typing import get_args

import pytest
from rich.default_styles import DEFAULT_STYLES
from rich.style import Style
from rich.text import Text

from iterm2_api_wrapper._logging import config, styles


def test_theme_style_vocabulary_matches_rich_and_wrapper_styles() -> None:
    rich_style_names = set(DEFAULT_STYLES)
    wrapper_style_names = {style.value for style in styles.LogStyle}

    assert set(get_args(styles.ThemeStyle)) == rich_style_names
    assert styles.ThemeStyles.__required_keys__ == frozenset()
    assert styles.ThemeStyles.__optional_keys__ == rich_style_names | wrapper_style_names


def test_style_spec_constructs_a_complete_rich_style() -> None:
    metadata = {"component": "api"}
    spec = styles.StyleSpec(
        color="bright_cyan",
        bgcolor="#101010",
        bold=True,
        italic=True,
        underline2=True,
        link="https://example.com",
        meta=metadata,
    )

    rich_style = spec.to_rich_style()

    assert rich_style.color == Style(color="bright_cyan").color
    assert rich_style.bgcolor == Style(bgcolor="#101010").bgcolor
    assert rich_style.bold is True
    assert rich_style.italic is True
    assert rich_style.underline2 is True
    assert rich_style.link == "https://example.com"
    assert rich_style.meta == metadata


def test_create_log_theme_accepts_typed_and_extensible_mappings() -> None:
    typed: styles.ThemeStyles = {
        "logging.level.info": styles.StyleSpec(color="green", bold=True),
        "log.success": "bold bright_green",
    }
    raw: dict[str, str] = {"application.custom": "underline magenta"}
    rich_styles = MappingProxyType({"application.rich": Style(color="yellow")})

    typed_theme = styles.create_log_theme(typed)
    raw_theme = styles.create_log_theme(raw)
    rich_theme = styles.create_log_theme(rich_styles)

    assert typed_theme.styles["logging.level.info"].bold is True
    assert raw_theme.styles["application.custom"].underline is True
    assert rich_theme.styles["application.rich"].color == Style(color="yellow").color


def test_create_log_theme_does_not_mutate_global_or_sibling_themes() -> None:
    original = styles.LOG_THEME.styles[styles.LogStyle.NUMBER.value]

    first = styles.create_log_theme({styles.LogStyle.NUMBER.value: "red"})
    second = styles.create_log_theme()

    assert first.styles[styles.LogStyle.NUMBER.value] != original
    assert second.styles[styles.LogStyle.NUMBER.value] == original
    assert styles.LOG_THEME.styles[styles.LogStyle.NUMBER.value] == original


def test_theme_and_gradient_inputs_are_validated() -> None:
    with pytest.raises(TypeError, match="theme styles must be"):
        styles._normalize_theme_value(object())
    with pytest.raises(ValueError, match="at least one color"):
        styles.gradient_colors([], 1)
    with pytest.raises(ValueError, match="greater than or equal to zero"):
        styles.gradient_colors(["red"], -1)
    with pytest.raises(ValueError, match="at least one color"):
        styles.GradientHighlighter([])
    with pytest.raises(ValueError, match="greater than or equal to zero"):
        styles.GradientHighlighter(["red"], max_chars=-1)

    assert styles.gradient_colors(["red"], 0) == []
    assert styles.gradient_colors(["#000000", "#ffffff"], 3) == ["rgb(0,0,0)", "rgb(127,127,127)", "rgb(255,255,255)"]


def test_semantic_highlighter_marks_common_log_tokens() -> None:
    text = Text(
        "SUCCESS WARNING ERROR FALSE NULL 42 25ms 0xFF "
        "123e4567-e89b-12d3-a456-426614174000 /tmp/output.log "
        "https://example.com/status"
    )

    styles.LogRegexHighlighter().highlight(text)
    applied_styles = {str(span.style) for span in text.spans}

    assert {
        "log.success",
        "log.warning",
        "log.failure",
        "log.bool",
        "log.none",
        "log.number",
        "log.duration",
        "log.hex",
        "log.uuid",
        "log.path",
        "log.url",
    } <= applied_styles
    url_start = text.plain.index("https://")
    assert not any(str(span.style) == "log.path" and span.start >= url_start for span in text.spans)


def test_default_level_profiles_keep_gradients_opt_in() -> None:
    assert all(profile.gradient is None for profile in styles.LEVEL_PROFILES.values())
    assert all(profile.highlighter is not None for profile in styles.LEVEL_PROFILES.values())


def test_default_and_merged_configs_are_mutation_isolated() -> None:
    first = config.get_default_log_config()
    second = config.get_default_log_config()

    assert first is not second
    for section in config.PrettyLogConfig.__optional_keys__:
        assert first[section] is not second[section]
    first_terminal = first.get("terminal_console_config")
    second_terminal = second.get("terminal_console_config")
    first_file = first.get("file_console_config")
    second_file = second.get("file_console_config")
    assert first_terminal is not None and second_terminal is not None
    assert first_file is not None and second_file is not None
    assert first_terminal.get("theme") is not second_terminal.get("theme")
    assert first_file.get("theme") is not second_file.get("theme")

    overrides: config.PrettyLogConfig = {
        "logger_config": {"source_link": "file"},
        "terminal_console_config": {"theme": styles.create_log_theme({"log.number": "red"})},
    }
    merged = config.merge_pretty_config(first, overrides)

    merged_logger = merged.get("logger_config")
    first_logger = first.get("logger_config")
    merged_terminal = merged.get("terminal_console_config")
    override_terminal = overrides.get("terminal_console_config")
    assert merged_logger is not None and first_logger is not None
    assert merged_terminal is not None and override_terminal is not None
    assert merged_logger.get("source_link") == "file"
    assert first_logger.get("source_link") == "vscode"
    assert merged_terminal is not first_terminal
    assert merged_terminal.get("theme") is not override_terminal.get("theme")
