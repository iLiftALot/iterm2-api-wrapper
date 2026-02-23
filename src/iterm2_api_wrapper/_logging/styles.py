from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, NamedTuple, Sequence

from rich.color import Color
from rich.color_triplet import ColorTriplet
from rich.highlighter import Highlighter, RegexHighlighter
from rich.style import Style
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
    "iso8601.date",
    "iso8601.time",
    "iso8601.timezone",
]
type ColorName = Literal[
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


type ColorLike = Color | ColorName | str


class StyleType(NamedTuple):
    """Structured style information for log styling."""

    color: ColorLike
    bgcolor: ColorLike
    attributes: tuple[StyleAttribute, ...] | None
    link: str | None


type StyleLike = ThemeStyle | StyleType | Style | str

# ---------- palette + gradient helpers ----------


def _to_triplet(color: ColorLike) -> ColorTriplet:
    if isinstance(color, Color):
        return color.get_truecolor()
    # string like "red" or "#ff00aa"
    return Color.parse(str(color)).get_truecolor()


def _lerp(a: int, b: int, t: float) -> int:
    return int(a + (b - a) * t)


def gradient_colors(stops: Sequence[ColorLike], steps: int) -> list[str]:
    if steps <= 1:
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
        self.stops = stops
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
    highlights: ClassVar[list[str]] = [
        r"(?P<number>\b\d+(\.\d+)?\b)",
        r"(?P<hex>0x[0-9a-fA-F]+)",
        r"(?P<uuid>\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b)",
        r"(?P<path>(?:/[\w\-.]+)+)",
        r"(?P<url>https?://\S+)",
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
    base: StyleLike | None = None  # ThemeStyle or Style object
    gradient: Sequence[ColorLike] | None = None
    highlighter: Highlighter | None = None


LEVEL_PROFILES: dict[str, LevelStyleProfile] = {
    "DEBUG": LevelStyleProfile(
        base="logging.level.debug",
        gradient=("#A809F2", "#0dccf6", "#10fabc"),
        highlighter=CompositeHighlighter(LogRegexHighlighter()),
    ),
    "INFO": LevelStyleProfile(
        base="logging.level.info",
        gradient=("#0cf943", "#85f819"),
        highlighter=CompositeHighlighter(LogRegexHighlighter()),
    ),
    "WARNING": LevelStyleProfile(
        base="logging.level.warning",
        gradient=("#ff9500", "#ebe707"),
        highlighter=CompositeHighlighter(LogRegexHighlighter()),
    ),
    "ERROR": LevelStyleProfile(
        base="logging.level.error",
        gradient=("#fb0b0b", "#f43f7e"),
        highlighter=CompositeHighlighter(LogRegexHighlighter()),
    ),
    "CRITICAL": LevelStyleProfile(
        base="logging.level.error",
        gradient=("#c70f0f", "#8ae907"),
        highlighter=CompositeHighlighter(LogRegexHighlighter()),
    ),
}


# ---------------- themes ----------------


LOG_THEME = Theme(
    {
        "log.number": "bold cyan",
        "log.hex": "magenta",
        "log.uuid": "dim green",
        "log.path": "yellow",
        "log.url": "underline blue",
    }
)
