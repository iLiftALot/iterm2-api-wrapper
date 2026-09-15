from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import ClassVar, Literal, TypedDict, overload

from rich.color import Color
from rich.color_triplet import ColorTriplet
from rich.highlighter import Highlighter, RegexHighlighter
from rich.style import Style
from rich.style import StyleType as RichStyleType
from rich.text import Text
from rich.theme import Theme


StyleAttribute = Literal[
    "dim",
    "d",
    "bold",
    "b",
    "italic",
    "i",
    "underline",
    "u",
    "blink",
    "blink2",
    "reverse",
    "r",
    "conceal",
    "c",
    "strike",
    "s",
    "underline2",
    "uu",
    "frame",
    "encircle",
    "overline",
    "o",
]
ThemeStyle = Literal[
    "none",
    "reset",
    "dim",
    "bright",
    "bold",
    "strong",
    "code",
    "italic",
    "emphasize",
    "underline",
    "blink",
    "blink2",
    "reverse",
    "strike",
    "black",
    "red",
    "green",
    "yellow",
    "magenta",
    "cyan",
    "white",
    "inspect.attr",
    "inspect.attr.dunder",
    "inspect.callable",
    "inspect.async_def",
    "inspect.def",
    "inspect.class",
    "inspect.error",
    "inspect.equals",
    "inspect.help",
    "inspect.doc",
    "inspect.value.border",
    "live.ellipsis",
    "layout.tree.row",
    "layout.tree.column",
    "logging.keyword",
    "logging.level.notset",
    "logging.level.debug",
    "logging.level.info",
    "logging.level.warning",
    "logging.level.error",
    "logging.level.critical",
    "log.level",
    "log.time",
    "log.message",
    "log.path",
    "repr.ellipsis",
    "repr.indent",
    "repr.error",
    "repr.str",
    "repr.brace",
    "repr.comma",
    "repr.ipv4",
    "repr.ipv6",
    "repr.eui48",
    "repr.eui64",
    "repr.tag_start",
    "repr.tag_name",
    "repr.tag_contents",
    "repr.tag_end",
    "repr.attrib_name",
    "repr.attrib_equal",
    "repr.attrib_value",
    "repr.number",
    "repr.number_complex",
    "repr.bool_true",
    "repr.bool_false",
    "repr.none",
    "repr.url",
    "repr.uuid",
    "repr.call",
    "repr.path",
    "repr.filename",
    "rule.line",
    "rule.text",
    "json.brace",
    "json.bool_true",
    "json.bool_false",
    "json.null",
    "json.number",
    "json.str",
    "json.key",
    "prompt",
    "prompt.choices",
    "prompt.default",
    "prompt.invalid",
    "prompt.invalid.choice",
    "pretty",
    "scope.border",
    "scope.key",
    "scope.key.special",
    "scope.equals",
    "table.header",
    "table.footer",
    "table.cell",
    "table.title",
    "table.caption",
    "traceback.error",
    "traceback.border.syntax_error",
    "traceback.border",
    "traceback.text",
    "traceback.title",
    "traceback.exc_type",
    "traceback.exc_value",
    "traceback.offset",
    "traceback.error_range",
    "traceback.note",
    "traceback.group.border",
    "bar.back",
    "bar.complete",
    "bar.finished",
    "bar.pulse",
    "progress.description",
    "progress.filesize",
    "progress.filesize.total",
    "progress.download",
    "progress.elapsed",
    "progress.percentage",
    "progress.remaining",
    "progress.data.speed",
    "progress.spinner",
    "status.spinner",
    "tree",
    "tree.line",
    "markdown.paragraph",
    "markdown.text",
    "markdown.em",
    "markdown.emph",
    "markdown.strong",
    "markdown.code",
    "markdown.code_block",
    "markdown.block_quote",
    "markdown.list",
    "markdown.item",
    "markdown.item.bullet",
    "markdown.item.number",
    "markdown.hr",
    "markdown.h1.border",
    "markdown.h1",
    "markdown.h2",
    "markdown.h3",
    "markdown.h4",
    "markdown.h5",
    "markdown.h6",
    "markdown.h7",
    "markdown.link",
    "markdown.link_url",
    "markdown.s",
    "markdown.table.border",
    "markdown.table.header",
    "markdown.kbd",
    "iso8601.date",
    "iso8601.time",
    "iso8601.timezone",
]
ColorName = Literal[
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
    "bright_black",
    "bright_red",
    "bright_green",
    "bright_yellow",
    "bright_blue",
    "bright_magenta",
    "bright_cyan",
    "bright_white",
    "grey0",
    "gray0",
    "navy_blue",
    "dark_blue",
    "blue3",
    "blue1",
    "dark_green",
    "deep_sky_blue4",
    "dodger_blue3",
    "dodger_blue2",
    "green4",
    "spring_green4",
    "turquoise4",
    "deep_sky_blue3",
    "dodger_blue1",
    "green3",
    "spring_green3",
    "dark_cyan",
    "light_sea_green",
    "deep_sky_blue2",
    "deep_sky_blue1",
    "spring_green2",
    "cyan3",
    "dark_turquoise",
    "turquoise2",
    "green1",
    "spring_green1",
    "medium_spring_green",
    "cyan2",
    "cyan1",
    "dark_red",
    "deep_pink4",
    "purple4",
    "purple3",
    "blue_violet",
    "orange4",
    "grey37",
    "gray37",
    "medium_purple4",
    "slate_blue3",
    "royal_blue1",
    "chartreuse4",
    "dark_sea_green4",
    "pale_turquoise4",
    "steel_blue",
    "steel_blue3",
    "cornflower_blue",
    "chartreuse3",
    "cadet_blue",
    "sky_blue3",
    "steel_blue1",
    "pale_green3",
    "sea_green3",
    "aquamarine3",
    "medium_turquoise",
    "chartreuse2",
    "sea_green2",
    "sea_green1",
    "aquamarine1",
    "dark_slate_gray2",
    "dark_magenta",
    "dark_violet",
    "purple",
    "light_pink4",
    "plum4",
    "medium_purple3",
    "slate_blue1",
    "yellow4",
    "wheat4",
    "grey53",
    "gray53",
    "light_slate_grey",
    "light_slate_gray",
    "medium_purple",
    "light_slate_blue",
    "dark_olive_green3",
    "dark_sea_green",
    "light_sky_blue3",
    "sky_blue2",
    "dark_sea_green3",
    "dark_slate_gray3",
    "sky_blue1",
    "chartreuse1",
    "light_green",
    "pale_green1",
    "dark_slate_gray1",
    "red3",
    "medium_violet_red",
    "magenta3",
    "dark_orange3",
    "indian_red",
    "hot_pink3",
    "medium_orchid3",
    "medium_orchid",
    "medium_purple2",
    "dark_goldenrod",
    "light_salmon3",
    "rosy_brown",
    "grey63",
    "gray63",
    "medium_purple1",
    "gold3",
    "dark_khaki",
    "navajo_white3",
    "grey69",
    "gray69",
    "light_steel_blue3",
    "light_steel_blue",
    "yellow3",
    "dark_sea_green2",
    "light_cyan3",
    "light_sky_blue1",
    "green_yellow",
    "dark_olive_green2",
    "dark_sea_green1",
    "pale_turquoise1",
    "deep_pink3",
    "magenta2",
    "hot_pink2",
    "orchid",
    "medium_orchid1",
    "orange3",
    "light_pink3",
    "pink3",
    "plum3",
    "violet",
    "light_goldenrod3",
    "tan",
    "misty_rose3",
    "thistle3",
    "plum2",
    "khaki3",
    "light_goldenrod2",
    "light_yellow3",
    "grey84",
    "gray84",
    "light_steel_blue1",
    "yellow2",
    "dark_olive_green1",
    "honeydew2",
    "light_cyan1",
    "red1",
    "deep_pink2",
    "deep_pink1",
    "magenta1",
    "orange_red1",
    "indian_red1",
    "hot_pink",
    "dark_orange",
    "salmon1",
    "light_coral",
    "pale_violet_red1",
    "orchid2",
    "orchid1",
    "orange1",
    "sandy_brown",
    "light_salmon1",
    "light_pink1",
    "pink1",
    "plum1",
    "gold1",
    "navajo_white1",
    "misty_rose1",
    "thistle1",
    "yellow1",
    "light_goldenrod1",
    "khaki1",
    "wheat1",
    "cornsilk1",
    "grey100",
    "gray100",
    "grey3",
    "gray3",
    "grey7",
    "gray7",
    "grey11",
    "gray11",
    "grey15",
    "gray15",
    "grey19",
    "gray19",
    "grey23",
    "gray23",
    "grey27",
    "gray27",
    "grey30",
    "gray30",
    "grey35",
    "gray35",
    "grey39",
    "gray39",
    "grey42",
    "gray42",
    "grey46",
    "gray46",
    "grey50",
    "gray50",
    "grey54",
    "gray54",
    "grey58",
    "gray58",
    "grey62",
    "gray62",
    "grey66",
    "gray66",
    "grey70",
    "gray70",
    "grey74",
    "gray74",
    "grey78",
    "gray78",
    "grey82",
    "gray82",
    "grey85",
    "gray85",
    "grey89",
    "gray89",
    "grey93",
    "gray93",
]


ColorLike = Color | ColorName | str


class LogStyle(str, Enum):
    """Semantic style names added by :mod:`iterm2_api_wrapper._logging`."""

    NUMBER = "log.number"
    HEX = "log.hex"
    UUID = "log.uuid"
    PATH = "log.path"
    URL = "log.url"
    DURATION = "log.duration"
    BOOLEAN = "log.bool"
    NONE = "log.none"
    SUCCESS = "log.success"
    WARNING = "log.warning"
    FAILURE = "log.failure"
    LOGGER = "log.logger"
    CONTEXT = "log.context"
    CONTEXT_KEY = "log.context.key"
    CONTEXT_VALUE = "log.context.value"
    RULE = "log.rule"


@dataclass(frozen=True, slots=True)
class StyleSpec:
    """A discoverable, immutable constructor for :class:`rich.style.Style`."""

    color: ColorLike | None = None
    bgcolor: ColorLike | None = None
    bold: bool | None = None
    dim: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    blink: bool | None = None
    blink2: bool | None = None
    reverse: bool | None = None
    conceal: bool | None = None
    strike: bool | None = None
    underline2: bool | None = None
    frame: bool | None = None
    encircle: bool | None = None
    overline: bool | None = None
    link: str | None = None
    meta: Mapping[str, object] | None = None

    def to_rich_style(self) -> Style:
        """Build a Rich style without exposing a mutable metadata mapping."""
        return Style(
            color=self.color,
            bgcolor=self.bgcolor,
            bold=self.bold,
            dim=self.dim,
            italic=self.italic,
            underline=self.underline,
            blink=self.blink,
            blink2=self.blink2,
            reverse=self.reverse,
            conceal=self.conceal,
            strike=self.strike,
            underline2=self.underline2,
            frame=self.frame,
            encircle=self.encircle,
            overline=self.overline,
            link=self.link,
            meta=dict(self.meta) if self.meta is not None else None,
        )


ThemeValue = StyleSpec | Style | str
StyleLike = ThemeStyle | LogStyle | StyleSpec | Style | str


ThemeStyles = TypedDict(
    "ThemeStyles",
    {
        "none": ThemeValue,
        "reset": ThemeValue,
        "dim": ThemeValue,
        "bright": ThemeValue,
        "bold": ThemeValue,
        "strong": ThemeValue,
        "code": ThemeValue,
        "italic": ThemeValue,
        "emphasize": ThemeValue,
        "underline": ThemeValue,
        "blink": ThemeValue,
        "blink2": ThemeValue,
        "reverse": ThemeValue,
        "strike": ThemeValue,
        "black": ThemeValue,
        "red": ThemeValue,
        "green": ThemeValue,
        "yellow": ThemeValue,
        "magenta": ThemeValue,
        "cyan": ThemeValue,
        "white": ThemeValue,
        "inspect.attr": ThemeValue,
        "inspect.attr.dunder": ThemeValue,
        "inspect.callable": ThemeValue,
        "inspect.async_def": ThemeValue,
        "inspect.def": ThemeValue,
        "inspect.class": ThemeValue,
        "inspect.error": ThemeValue,
        "inspect.equals": ThemeValue,
        "inspect.help": ThemeValue,
        "inspect.doc": ThemeValue,
        "inspect.value.border": ThemeValue,
        "live.ellipsis": ThemeValue,
        "layout.tree.row": ThemeValue,
        "layout.tree.column": ThemeValue,
        "logging.keyword": ThemeValue,
        "logging.level.notset": ThemeValue,
        "logging.level.debug": ThemeValue,
        "logging.level.info": ThemeValue,
        "logging.level.warning": ThemeValue,
        "logging.level.error": ThemeValue,
        "logging.level.critical": ThemeValue,
        "log.level": ThemeValue,
        "log.time": ThemeValue,
        "log.message": ThemeValue,
        "log.path": ThemeValue,
        "repr.ellipsis": ThemeValue,
        "repr.indent": ThemeValue,
        "repr.error": ThemeValue,
        "repr.str": ThemeValue,
        "repr.brace": ThemeValue,
        "repr.comma": ThemeValue,
        "repr.ipv4": ThemeValue,
        "repr.ipv6": ThemeValue,
        "repr.eui48": ThemeValue,
        "repr.eui64": ThemeValue,
        "repr.tag_start": ThemeValue,
        "repr.tag_name": ThemeValue,
        "repr.tag_contents": ThemeValue,
        "repr.tag_end": ThemeValue,
        "repr.attrib_name": ThemeValue,
        "repr.attrib_equal": ThemeValue,
        "repr.attrib_value": ThemeValue,
        "repr.number": ThemeValue,
        "repr.number_complex": ThemeValue,
        "repr.bool_true": ThemeValue,
        "repr.bool_false": ThemeValue,
        "repr.none": ThemeValue,
        "repr.url": ThemeValue,
        "repr.uuid": ThemeValue,
        "repr.call": ThemeValue,
        "repr.path": ThemeValue,
        "repr.filename": ThemeValue,
        "rule.line": ThemeValue,
        "rule.text": ThemeValue,
        "json.brace": ThemeValue,
        "json.bool_true": ThemeValue,
        "json.bool_false": ThemeValue,
        "json.null": ThemeValue,
        "json.number": ThemeValue,
        "json.str": ThemeValue,
        "json.key": ThemeValue,
        "prompt": ThemeValue,
        "prompt.choices": ThemeValue,
        "prompt.default": ThemeValue,
        "prompt.invalid": ThemeValue,
        "prompt.invalid.choice": ThemeValue,
        "pretty": ThemeValue,
        "scope.border": ThemeValue,
        "scope.key": ThemeValue,
        "scope.key.special": ThemeValue,
        "scope.equals": ThemeValue,
        "table.header": ThemeValue,
        "table.footer": ThemeValue,
        "table.cell": ThemeValue,
        "table.title": ThemeValue,
        "table.caption": ThemeValue,
        "traceback.error": ThemeValue,
        "traceback.border.syntax_error": ThemeValue,
        "traceback.border": ThemeValue,
        "traceback.text": ThemeValue,
        "traceback.title": ThemeValue,
        "traceback.exc_type": ThemeValue,
        "traceback.exc_value": ThemeValue,
        "traceback.offset": ThemeValue,
        "traceback.error_range": ThemeValue,
        "traceback.note": ThemeValue,
        "traceback.group.border": ThemeValue,
        "bar.back": ThemeValue,
        "bar.complete": ThemeValue,
        "bar.finished": ThemeValue,
        "bar.pulse": ThemeValue,
        "progress.description": ThemeValue,
        "progress.filesize": ThemeValue,
        "progress.filesize.total": ThemeValue,
        "progress.download": ThemeValue,
        "progress.elapsed": ThemeValue,
        "progress.percentage": ThemeValue,
        "progress.remaining": ThemeValue,
        "progress.data.speed": ThemeValue,
        "progress.spinner": ThemeValue,
        "status.spinner": ThemeValue,
        "tree": ThemeValue,
        "tree.line": ThemeValue,
        "markdown.paragraph": ThemeValue,
        "markdown.text": ThemeValue,
        "markdown.em": ThemeValue,
        "markdown.emph": ThemeValue,
        "markdown.strong": ThemeValue,
        "markdown.code": ThemeValue,
        "markdown.code_block": ThemeValue,
        "markdown.block_quote": ThemeValue,
        "markdown.list": ThemeValue,
        "markdown.item": ThemeValue,
        "markdown.item.bullet": ThemeValue,
        "markdown.item.number": ThemeValue,
        "markdown.hr": ThemeValue,
        "markdown.h1.border": ThemeValue,
        "markdown.h1": ThemeValue,
        "markdown.h2": ThemeValue,
        "markdown.h3": ThemeValue,
        "markdown.h4": ThemeValue,
        "markdown.h5": ThemeValue,
        "markdown.h6": ThemeValue,
        "markdown.h7": ThemeValue,
        "markdown.link": ThemeValue,
        "markdown.link_url": ThemeValue,
        "markdown.s": ThemeValue,
        "markdown.table.border": ThemeValue,
        "markdown.table.header": ThemeValue,
        "markdown.kbd": ThemeValue,
        "iso8601.date": ThemeValue,
        "iso8601.time": ThemeValue,
        "iso8601.timezone": ThemeValue,
        "log.number": ThemeValue,
        "log.hex": ThemeValue,
        "log.uuid": ThemeValue,
        "log.url": ThemeValue,
        "log.duration": ThemeValue,
        "log.bool": ThemeValue,
        "log.none": ThemeValue,
        "log.success": ThemeValue,
        "log.warning": ThemeValue,
        "log.failure": ThemeValue,
        "log.logger": ThemeValue,
        "log.context": ThemeValue,
        "log.context.key": ThemeValue,
        "log.context.value": ThemeValue,
        "log.rule": ThemeValue,
    },
    total=False,
)

# ---------- palette + gradient helpers ----------


def _to_triplet(color: ColorLike) -> ColorTriplet:
    if isinstance(color, Color):
        return color.get_truecolor()
    # string like "red" or "#ff00aa"
    return Color.parse(str(color)).get_truecolor()


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def gradient_colors(stops: Sequence[ColorLike], steps: int) -> list[str]:
    if not stops:
        raise ValueError("gradient stops must contain at least one color")
    if steps < 0:
        raise ValueError("gradient steps must be greater than or equal to zero")
    if steps == 0:
        return []
    if steps == 1:
        return [str(stops[0])]
    # expand across multiple stops
    triplets = [_to_triplet(c) for c in stops]
    segments = len(triplets) - 1
    if segments <= 0:
        return [str(stops[0])] * steps

    colors: list[str] = []
    for i in range(steps):
        t = i / max(steps - 1, 1)
        seg = min(int(t * segments), segments - 1)
        local_t = (t - (seg / segments)) * segments
        a = triplets[seg]
        b = triplets[seg + 1]
        r = _lerp(a.red, b.red, local_t)
        g = _lerp(a.green, b.green, local_t)
        b_ = _lerp(a.blue, b.blue, local_t)
        colors.append(f"rgb({r},{g},{b_})")
    return colors


# ---------- highlighters ----------


class GradientHighlighter(Highlighter):
    def __init__(self, stops: Sequence[ColorLike], max_chars: int = 200) -> None:
        if not stops:
            raise ValueError("gradient stops must contain at least one color")
        if max_chars < 0:
            raise ValueError("max_chars must be greater than or equal to zero")
        self.stops = tuple(stops)
        self.max_chars = max_chars

    def highlight(self, text: Text) -> None:
        plain = text.plain
        length = min(len(plain), self.max_chars)
        if length <= 1:
            return
        colors = gradient_colors(self.stops, length)
        for i in range(length):
            text.stylize(colors[i], i, i + 1)


class LogRegexHighlighter(RegexHighlighter):
    base_style = "log."
    highlights: ClassVar[Sequence[str]] = [
        r"(?P<url>\b(?:https?|wss?|file)://[^\s<>]+)",
        r"(?P<uuid>\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b)",
        r"(?P<hex>\b0x[0-9a-fA-F]+\b)",
        r"(?P<duration>\b\d+(?:\.\d+)?\s?(?:ns|us|µs|ms|s|sec|secs|m|min|mins|h|hr|hrs)\b)",
        r"\b(?P<bool>(?i:true|false))\b",
        r"\b(?P<none>(?i:none|null))\b",
        r"\b(?P<success>(?i:success(?:ful)?|succeeded|passed|complete(?:d)?|ok))\b",
        r"\b(?P<warning>(?i:warn(?:ing)?|caution|retry(?:ing)?))\b",
        r"\b(?P<failure>(?i:fail(?:ed|ure)?|error|exception|critical|fatal))\b",
        r"(?P<path>(?<![\w:/])(?:~|\.{0,2})?/(?:[-\w.@+]+/)*[-\w.@+]*)",
        r"(?P<number>(?<![\w.])-?\d+(?:\.\d+)?(?:e[+-]?\d+)?\b)",
    ]


class CompositeHighlighter(Highlighter):
    def __init__(self, *highlighters: Highlighter) -> None:
        self._highlighters = highlighters

    def highlight(self, text: Text) -> None:
        for h in self._highlighters:
            h.highlight(text)


# ---------- per-level profiles ----------


@dataclass(frozen=True)
class LevelStyleProfile:
    base: StyleLike | None = None
    gradient: Sequence[ColorLike] | None = None
    highlighter: Highlighter | None = None


LogLevelName = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


LEVEL_PROFILES: dict[str, LevelStyleProfile] = {
    "DEBUG": LevelStyleProfile(base="logging.level.debug", highlighter=CompositeHighlighter(LogRegexHighlighter())),
    "INFO": LevelStyleProfile(base="logging.level.info", highlighter=CompositeHighlighter(LogRegexHighlighter())),
    "WARNING": LevelStyleProfile(base="logging.level.warning", highlighter=CompositeHighlighter(LogRegexHighlighter())),
    "ERROR": LevelStyleProfile(base="logging.level.error", highlighter=CompositeHighlighter(LogRegexHighlighter())),
    "CRITICAL": LevelStyleProfile(
        base="logging.level.critical", highlighter=CompositeHighlighter(LogRegexHighlighter())
    ),
}


_LOG_THEME_DEFAULTS: Mapping[str, ThemeValue] = MappingProxyType(
    {
        "logging.level.debug": StyleSpec(color="bright_black", dim=True),
        "logging.level.info": StyleSpec(color="bright_blue", bold=True),
        "logging.level.warning": StyleSpec(color="bright_yellow", bold=True),
        "logging.level.error": StyleSpec(color="bright_red", bold=True),
        "logging.level.critical": StyleSpec(color="white", bgcolor="red", bold=True),
        "log.time": StyleSpec(color="bright_black", dim=True),
        "log.path": StyleSpec(color="cyan", dim=True),
        LogStyle.NUMBER.value: StyleSpec(color="bright_cyan", bold=True),
        LogStyle.HEX.value: StyleSpec(color="magenta", bold=True),
        LogStyle.UUID.value: StyleSpec(color="green", dim=True),
        LogStyle.URL.value: StyleSpec(color="bright_blue", underline=True),
        LogStyle.DURATION.value: StyleSpec(color="cyan", bold=True),
        LogStyle.BOOLEAN.value: StyleSpec(color="magenta"),
        LogStyle.NONE.value: StyleSpec(color="bright_black", italic=True),
        LogStyle.SUCCESS.value: StyleSpec(color="bright_green", bold=True),
        LogStyle.WARNING.value: StyleSpec(color="bright_yellow", bold=True),
        LogStyle.FAILURE.value: StyleSpec(color="bright_red", bold=True),
        LogStyle.LOGGER.value: StyleSpec(color="bright_blue", bold=True),
        LogStyle.CONTEXT.value: StyleSpec(color="cyan", dim=True),
        LogStyle.CONTEXT_KEY.value: StyleSpec(color="cyan"),
        LogStyle.CONTEXT_VALUE.value: StyleSpec(color="white"),
        LogStyle.RULE.value: StyleSpec(color="bright_black", dim=True),
    }
)


def _normalize_theme_value(value: object) -> RichStyleType:
    if isinstance(value, StyleSpec):
        return value.to_rich_style()
    if isinstance(value, (Style, str)):
        return value
    raise TypeError(f"theme styles must be str, Style, or StyleSpec, not {type(value).__name__}")


@overload
def create_log_theme(overrides: ThemeStyles, *, inherit: bool = True) -> Theme: ...


@overload
def create_log_theme(overrides: Mapping[str, ThemeValue] | None = None, *, inherit: bool = True) -> Theme: ...


def create_log_theme(overrides: ThemeStyles | Mapping[str, ThemeValue] | None = None, *, inherit: bool = True) -> Theme:
    """Create an isolated Rich theme from wrapper defaults and caller overrides."""
    styles: dict[str, RichStyleType] = {
        name: _normalize_theme_value(value) for name, value in _LOG_THEME_DEFAULTS.items()
    }
    if overrides is not None:
        styles.update({name: _normalize_theme_value(value) for name, value in overrides.items()})
    return Theme(styles, inherit=inherit)


LOG_THEME = create_log_theme()
