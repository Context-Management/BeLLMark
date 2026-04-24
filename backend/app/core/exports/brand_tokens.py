"""Brand token foundation — single source of truth for BeLLMark export styling.

This module mirrors `frontend/src/index.css` (`:root` + `.dark`) into Python by
hand-translating every OKLCH value to opaque sRGB via a deterministic
OKLCH → OKLab → linear sRGB → gamma-encoded sRGB pipeline (no optional
third-party fallback). Alpha-bearing tokens are pre-composited against the
appropriate background token.

Consumed by sf-02 (html_export), sf-03 (pdf_export), sf-04 (pptx_export).
sf-01 owns this file + the legacy `themes.py` shim that delegates here.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Literal, TypedDict

ThemeName = Literal["light", "dark"]


class BrandTokens(TypedDict):
    # Neutrals
    background: tuple[int, int, int]
    foreground: tuple[int, int, int]
    card: tuple[int, int, int]
    card_foreground: tuple[int, int, int]
    popover: tuple[int, int, int]
    popover_foreground: tuple[int, int, int]
    primary: tuple[int, int, int]
    primary_foreground: tuple[int, int, int]
    secondary: tuple[int, int, int]
    secondary_foreground: tuple[int, int, int]
    muted: tuple[int, int, int]
    muted_foreground: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent_foreground: tuple[int, int, int]
    destructive: tuple[int, int, int]
    border: tuple[int, int, int]
    input: tuple[int, int, int]
    ring: tuple[int, int, int]
    # Chart palette — distinct from accent; NOT aliased.
    chart_1: tuple[int, int, int]
    chart_2: tuple[int, int, int]
    chart_3: tuple[int, int, int]
    chart_4: tuple[int, int, int]
    chart_5: tuple[int, int, int]
    # Radii (logical px at 1920×1080)
    radius_sm: float
    radius_md: float
    radius_lg: float
    # Typography scale (logical px at 1920×1080)
    font_title: int
    font_h2: int
    font_body: int
    font_caption: int
    font_footer: int


# Color-token allowlist — single source of truth, used by implementation
# AND tests. Mirrors COLOR custom properties from frontend/src/index.css
# (`:root` for light, `.dark` for dark). Excludes `sidebar*` variants —
# export slide decks do not use sidebar context.
COLOR_TOKEN_ALLOWLIST: tuple[str, ...] = (
    "background", "foreground",
    "card", "card_foreground",
    "popover", "popover_foreground",
    "primary", "primary_foreground",
    "secondary", "secondary_foreground",
    "muted", "muted_foreground",
    "accent", "accent_foreground",
    "destructive",
    "border", "input", "ring",
    "chart_1", "chart_2", "chart_3", "chart_4", "chart_5",
)


# ---------------------------------------------------------------------------
# OKLCH → sRGB conversion (hand-implemented — no external library)
# ---------------------------------------------------------------------------
#
# Pipeline:
#   1. OKLCH → OKLab (polar → cartesian)
#      a = C * cos(h_rad), b = C * sin(h_rad)
#   2. OKLab → linear sRGB (Björn Ottosson's published matrices)
#   3. Linear sRGB → gamma-encoded sRGB (piecewise: 12.92·x below 0.0031308,
#      else 1.055·x^(1/2.4) − 0.055)
#
# Reference vectors (verified against https://oklch.com and CSS Color 4 spec):
#   oklch(1, 0, 0)          → sRGB (255, 255, 255)
#   oklch(0, 0, 0)          → sRGB   (0,   0,   0)
#   oklch(0.145, 0, 0)      → sRGB  (10,  10,  10)
#   oklch(0.205, 0, 0)      → sRGB  (23,  23,  23)
#   oklch(0.269, 0, 0)      → sRGB  (38,  38,  38)
#   oklch(0.985, 0, 0)      → sRGB (250, 250, 250)
#   oklch(0.922, 0, 0)      → sRGB (229, 229, 229)
#   oklch(0.577 0.245 27.325)  → ≈ destructive red
#   oklch(0.646 0.222 41.116)  → ≈ chart-1 light (warm orange)
# ---------------------------------------------------------------------------


def _srgb_gamma_encode(x: float) -> float:
    """Linear sRGB (0..1) → gamma-encoded sRGB (0..1), clamped to [0,1]."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x <= 0.0031308:
        return 12.92 * x
    return 1.055 * (x ** (1.0 / 2.4)) - 0.055


def oklch_to_rgb(
    l: float,
    c: float,
    h: float,
    alpha: float = 1.0,  # noqa: ARG001 — retained for signature parity; not used for opaque output
) -> tuple[int, int, int]:
    """Convert an OKLCH triple to opaque 8-bit sRGB.

    Args:
        l: Perceptual lightness, 0..1.
        c: Chroma, typically 0..0.4.
        h: Hue in degrees.
        alpha: Accepted for API symmetry with CSS notation; ignored — caller is
            expected to pre-composite via ``alpha_composite`` when needed.

    Returns:
        Tuple ``(r, g, b)`` with channels in 0..255.
    """
    # 1) OKLCH → OKLab (polar → cartesian)
    h_rad = math.radians(h)
    a = c * math.cos(h_rad)
    b_lab = c * math.sin(h_rad)

    # 2) OKLab → linear sRGB (Ottosson 2020)
    l_ = l + 0.3963377774 * a + 0.2158037573 * b_lab
    m_ = l - 0.1055613458 * a - 0.0638541728 * b_lab
    s_ = l - 0.0894841775 * a - 1.2914855480 * b_lab

    L3 = l_ * l_ * l_
    M3 = m_ * m_ * m_
    S3 = s_ * s_ * s_

    r_lin = 4.0767416621 * L3 - 3.3077115913 * M3 + 0.2309699292 * S3
    g_lin = -1.2684380046 * L3 + 2.6097574011 * M3 - 0.3413193965 * S3
    b_lin = -0.0041960863 * L3 - 0.7034186147 * M3 + 1.7076147010 * S3

    # 3) Linear sRGB → gamma-encoded sRGB
    r = _srgb_gamma_encode(r_lin)
    g = _srgb_gamma_encode(g_lin)
    b = _srgb_gamma_encode(b_lin)

    return (round(r * 255), round(g * 255), round(b * 255))


def alpha_composite(
    top_rgb: tuple[int, int, int],
    bottom_rgb: tuple[int, int, int],
    alpha: float,
) -> tuple[int, int, int]:
    """Pre-composite a partially-transparent foreground over an opaque background.

    Uses the straight-alpha formula per channel::

        out = round(alpha * top + (1 - alpha) * bottom)

    Needed because exports emit opaque sRGB only, but CSS tokens such as the
    dark-mode ``--border`` (``oklch(1 0 0 / 10%)``) carry alpha. We resolve
    them once here against the matching background token.
    """
    a = max(0.0, min(1.0, float(alpha)))
    return (
        round(a * top_rgb[0] + (1.0 - a) * bottom_rgb[0]),
        round(a * top_rgb[1] + (1.0 - a) * bottom_rgb[1]),
        round(a * top_rgb[2] + (1.0 - a) * bottom_rgb[2]),
    )


# ---------------------------------------------------------------------------
# Token tables — resolved eagerly at import time
# ---------------------------------------------------------------------------

# Light mode.
#
# The shadcn `--background` in `frontend/src/index.css` is pure white, but
# the actual BeLLMark Layout component (`frontend/src/components/Layout.tsx`)
# overrides it with Tailwind's `bg-stone-100` (#F5F5F4 — warm off-white)
# for the page body and `bg-stone-50` (#FAFAF9) for headers/sidebar. Exports
# must match what the user SEES in the app, not the shadcn theoretical token,
# so we resolve the visible surface colors to Tailwind's stone palette.
_LIGHT_BACKGROUND = (0xF5, 0xF5, 0xF4)  # stone-100 — page body
_LIGHT_FOREGROUND = (0x11, 0x18, 0x27)  # gray-900 — body text (Layout.tsx)
_LIGHT_CARD = (0xFA, 0xFA, 0xF9)        # stone-50 — card/header surface
_LIGHT_CARD_FOREGROUND = (0x11, 0x18, 0x27)
_LIGHT_POPOVER = (0xFA, 0xFA, 0xF9)
_LIGHT_POPOVER_FOREGROUND = (0x11, 0x18, 0x27)
_LIGHT_PRIMARY = (0x11, 0x18, 0x27)     # gray-900
_LIGHT_PRIMARY_FOREGROUND = (0xFA, 0xFA, 0xF9)
_LIGHT_SECONDARY = (0xE7, 0xE5, 0xE4)   # stone-200 — secondary surfaces
_LIGHT_SECONDARY_FOREGROUND = (0x11, 0x18, 0x27)
_LIGHT_MUTED = (0xE7, 0xE5, 0xE4)       # stone-200
_LIGHT_MUTED_FOREGROUND = (0x6B, 0x72, 0x80)  # gray-500 — muted body text
_LIGHT_ACCENT = (0xE7, 0xE5, 0xE4)      # stone-200 (layout token, NOT brand accent)
_LIGHT_ACCENT_FOREGROUND = (0x11, 0x18, 0x27)
_LIGHT_DESTRUCTIVE = oklch_to_rgb(0.577, 0.245, 27.325)
_LIGHT_BORDER = (0xE7, 0xE5, 0xE4)      # stone-200
_LIGHT_INPUT = (0xE7, 0xE5, 0xE4)
_LIGHT_RING = (0xA8, 0xA2, 0x9E)        # stone-400
_LIGHT_CHART_1 = oklch_to_rgb(0.646, 0.222, 41.116)
_LIGHT_CHART_2 = oklch_to_rgb(0.6, 0.118, 184.704)
_LIGHT_CHART_3 = oklch_to_rgb(0.398, 0.07, 227.392)
_LIGHT_CHART_4 = oklch_to_rgb(0.828, 0.189, 84.429)
_LIGHT_CHART_5 = oklch_to_rgb(0.769, 0.188, 70.08)

# Dark mode.
#
# Same story as light: Layout.tsx uses Tailwind's `bg-gray-900` (#111827 —
# dark navy-slate) for page body and `bg-gray-950` (#030712 — near-black)
# for header/sidebar. This is the actual user-visible dark theme; the
# shadcn `.dark --background` (pure charcoal with zero chroma) is unused.
_DARK_BACKGROUND = (0x11, 0x18, 0x27)   # gray-900 — dark navy, page body
_DARK_FOREGROUND = (0xFF, 0xFF, 0xFF)   # white — body text
_DARK_CARD = (0x03, 0x07, 0x12)         # gray-950 — card/header surface
_DARK_CARD_FOREGROUND = (0xFF, 0xFF, 0xFF)
_DARK_POPOVER = (0x03, 0x07, 0x12)
_DARK_POPOVER_FOREGROUND = (0xFF, 0xFF, 0xFF)
_DARK_PRIMARY = (0xFF, 0xFF, 0xFF)
_DARK_PRIMARY_FOREGROUND = (0x11, 0x18, 0x27)
_DARK_SECONDARY = (0x1F, 0x29, 0x37)    # gray-800 — secondary surfaces
_DARK_SECONDARY_FOREGROUND = (0xFF, 0xFF, 0xFF)
_DARK_MUTED = (0x1F, 0x29, 0x37)        # gray-800
_DARK_MUTED_FOREGROUND = (0x9C, 0xA3, 0xAF)  # gray-400 — muted body text
_DARK_ACCENT = (0x1F, 0x29, 0x37)
_DARK_ACCENT_FOREGROUND = (0xFF, 0xFF, 0xFF)
_DARK_DESTRUCTIVE = oklch_to_rgb(0.704, 0.191, 22.216)
_DARK_BORDER = (0x1F, 0x29, 0x37)       # gray-800
_DARK_INPUT = (0x37, 0x41, 0x51)        # gray-700
_DARK_RING = (0x6B, 0x72, 0x80)         # gray-500
_DARK_CHART_1 = oklch_to_rgb(0.488, 0.243, 264.376)
_DARK_CHART_2 = oklch_to_rgb(0.696, 0.17, 162.48)
_DARK_CHART_3 = oklch_to_rgb(0.769, 0.188, 70.08)
_DARK_CHART_4 = oklch_to_rgb(0.627, 0.265, 303.9)
_DARK_CHART_5 = oklch_to_rgb(0.645, 0.246, 16.439)

# Typography + radii — canvas-native px values (mockups are 1920×1080).
_FONT_TITLE = 84
_FONT_H2 = 30
_FONT_BODY = 14
_FONT_CAPTION = 13
_FONT_FOOTER = 12

# --radius: 0.625rem = 10 px at 16 px root; Tailwind inline scale.
_RADIUS_LG = 10.0  # var(--radius)
_RADIUS_MD = 8.0  # var(--radius) - 2px
_RADIUS_SM = 6.0  # var(--radius) - 4px


_LIGHT_TOKENS: BrandTokens = {
    "background": _LIGHT_BACKGROUND,
    "foreground": _LIGHT_FOREGROUND,
    "card": _LIGHT_CARD,
    "card_foreground": _LIGHT_CARD_FOREGROUND,
    "popover": _LIGHT_POPOVER,
    "popover_foreground": _LIGHT_POPOVER_FOREGROUND,
    "primary": _LIGHT_PRIMARY,
    "primary_foreground": _LIGHT_PRIMARY_FOREGROUND,
    "secondary": _LIGHT_SECONDARY,
    "secondary_foreground": _LIGHT_SECONDARY_FOREGROUND,
    "muted": _LIGHT_MUTED,
    "muted_foreground": _LIGHT_MUTED_FOREGROUND,
    "accent": _LIGHT_ACCENT,
    "accent_foreground": _LIGHT_ACCENT_FOREGROUND,
    "destructive": _LIGHT_DESTRUCTIVE,
    "border": _LIGHT_BORDER,
    "input": _LIGHT_INPUT,
    "ring": _LIGHT_RING,
    "chart_1": _LIGHT_CHART_1,
    "chart_2": _LIGHT_CHART_2,
    "chart_3": _LIGHT_CHART_3,
    "chart_4": _LIGHT_CHART_4,
    "chart_5": _LIGHT_CHART_5,
    "radius_sm": _RADIUS_SM,
    "radius_md": _RADIUS_MD,
    "radius_lg": _RADIUS_LG,
    "font_title": _FONT_TITLE,
    "font_h2": _FONT_H2,
    "font_body": _FONT_BODY,
    "font_caption": _FONT_CAPTION,
    "font_footer": _FONT_FOOTER,
}

_DARK_TOKENS: BrandTokens = {
    "background": _DARK_BACKGROUND,
    "foreground": _DARK_FOREGROUND,
    "card": _DARK_CARD,
    "card_foreground": _DARK_CARD_FOREGROUND,
    "popover": _DARK_POPOVER,
    "popover_foreground": _DARK_POPOVER_FOREGROUND,
    "primary": _DARK_PRIMARY,
    "primary_foreground": _DARK_PRIMARY_FOREGROUND,
    "secondary": _DARK_SECONDARY,
    "secondary_foreground": _DARK_SECONDARY_FOREGROUND,
    "muted": _DARK_MUTED,
    "muted_foreground": _DARK_MUTED_FOREGROUND,
    "accent": _DARK_ACCENT,
    "accent_foreground": _DARK_ACCENT_FOREGROUND,
    "destructive": _DARK_DESTRUCTIVE,
    "border": _DARK_BORDER,
    "input": _DARK_INPUT,
    "ring": _DARK_RING,
    "chart_1": _DARK_CHART_1,
    "chart_2": _DARK_CHART_2,
    "chart_3": _DARK_CHART_3,
    "chart_4": _DARK_CHART_4,
    "chart_5": _DARK_CHART_5,
    "radius_sm": _RADIUS_SM,
    "radius_md": _RADIUS_MD,
    "radius_lg": _RADIUS_LG,
    "font_title": _FONT_TITLE,
    "font_h2": _FONT_H2,
    "font_body": _FONT_BODY,
    "font_caption": _FONT_CAPTION,
    "font_footer": _FONT_FOOTER,
}


# Frontend visual-brand colors — Tailwind v3 hex values taken verbatim
# from the classes `frontend/src/pages/results/OverviewSection.tsx` uses
# to color the winner row, runner-ups, criteria badges, and judge badges.
# Exports must match these exactly — the shadcn neutral `--accent` is a
# layout token, NOT a visual accent. For visual accents, use FRONTEND_BRAND.
FRONTEND_BRAND: dict[str, dict[str, tuple[int, int, int]]] = {
    "light": {
        # winner rank=1: `text-amber-600` = #D97706
        "winner_text":    (0xD9, 0x77, 0x06),
        # other ranks: `text-green-600` = #16A34A
        "runner_text":    (0x16, 0xA3, 0x4A),
        # rank=3 bronze: `text-orange-600` = #EA580C
        "bronze_text":    (0xEA, 0x58, 0x0C),
        # criteria badge: text amber-700 / bg amber-100 / border amber-300
        "criteria_text":  (0xB4, 0x53, 0x09),
        "criteria_bg":    (0xFE, 0xF3, 0xC7),
        "criteria_bord":  (0xFC, 0xD3, 0x4D),
        # judge badge: text purple-700 / bg purple-100 / border purple-300
        "judge_text":     (0x7E, 0x22, 0xCE),
        "judge_bg":       (0xF3, 0xE8, 0xFF),
        "judge_bord":     (0xD8, 0xB4, 0xFE),
        # winner-card gradient endpoints — amber-50 / yellow-50 (Tailwind)
        "winner_card_a":  (0xFF, 0xFB, 0xEB),  # amber-50
        "winner_card_b":  (0xFE, 0xFC, 0xE8),  # yellow-50
        "winner_card_bd": (0xFC, 0xD3, 0x4D),  # amber-300
        # heatmap anchors (score cells, frontend does red→amber→green)
        "heat_bad":       (0xFE, 0xCA, 0xCA),  # red-200
        "heat_mid":       (0xFE, 0xF0, 0x8A),  # yellow-200
        "heat_good":      (0xBB, 0xF7, 0xD0),  # green-200
        # length-bias / warning amber
        "warn_text":      (0xD9, 0x77, 0x06),  # amber-600
    },
    "dark": {
        # winner: `dark:text-yellow-400` = #FACC15
        "winner_text":    (0xFA, 0xCC, 0x15),
        # others: `dark:text-green-400` = #4ADE80
        "runner_text":    (0x4A, 0xDE, 0x80),
        "bronze_text":    (0xFB, 0x92, 0x3C),  # orange-400
        # criteria dark: amber-300 @ 90% / amber-900 @ 30% / amber-700 @ 30%
        "criteria_text":  (0xFC, 0xD3, 0x4D),  # amber-300
        "criteria_bg":    (0x3E, 0x25, 0x0B),  # amber-900 @ 30% over near-black
        "criteria_bord":  (0x4C, 0x30, 0x0E),  # amber-700 @ 30% over near-black
        # judge dark: purple-300 @ 90% / purple-900 @ 30% / purple-700 @ 30%
        "judge_text":     (0xD8, 0xB4, 0xFE),
        "judge_bg":       (0x2C, 0x10, 0x40),  # purple-900 @ 30% over dark bg
        "judge_bord":     (0x3F, 0x1B, 0x5C),  # purple-700 @ 30% over dark bg
        # winner-card dark gradient: yellow-900 @ 30% → amber-900 @ 30%,
        # composited visually over the gray-900 body background.
        "winner_card_a":  (0x34, 0x29, 0x13),  # yellow-900 30% over gray-900
        "winner_card_b":  (0x34, 0x22, 0x11),  # amber-900 30% over gray-900
        "winner_card_bd": (0xEA, 0xB3, 0x08),  # yellow-500 border
        # heatmap anchors — muted variants for dark
        "heat_bad":       (0x45, 0x1A, 0x1A),
        "heat_mid":       (0x4A, 0x3A, 0x10),
        "heat_good":      (0x14, 0x3C, 0x28),
        "warn_text":      (0xFC, 0xD3, 0x4D),  # amber-300
    },
}


def brand(theme: ThemeName, key: str) -> tuple[int, int, int]:
    """Look up a frontend-brand color. Raises KeyError if unknown."""
    return FRONTEND_BRAND[theme][key]


def token_hex(rgb: tuple[int, int, int]) -> str:
    """Convert an 8-bit sRGB triple to ``#RRGGBB`` uppercase.

    Used by HTML/PDF exporters to bake explicit stroke attributes onto SVG
    markup, by the PNG asset generator, and by guard tests.
    """
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _fmt_latency_ms(ms: float | int | None) -> str:
    """Format a millisecond latency value for leaderboard cells.

    Returns ``"—"`` for missing/non-positive values, otherwise picks the
    most compact human-readable unit: ``Xms`` / ``X.Xs`` / ``Xm Ys`` /
    ``Xh Ym``. Shared by HTML and PPTX leaderboard renderers.
    """
    if ms is None:
        return "—"
    try:
        ms_f = float(ms)
    except (TypeError, ValueError):
        return "—"
    if ms_f <= 0:
        return "—"
    if ms_f < 1000:
        return f"{ms_f:.0f}ms"
    if ms_f < 60_000:
        return f"{ms_f / 1000:.1f}s"
    if ms_f < 3_600_000:
        mins = int(ms_f // 60_000)
        secs = int((ms_f % 60_000) / 1000)
        return f"{mins}m {secs}s"
    hrs = int(ms_f // 3_600_000)
    mins = int((ms_f % 3_600_000) / 60_000)
    return f"{hrs}h {mins}m"


def get_tokens(theme: ThemeName) -> BrandTokens:
    """Return the fully-populated brand-token dict for ``theme``.

    Raises:
        ValueError: if ``theme`` is not one of ``"light"``/``"dark"``.
    """
    if theme == "light":
        # Copy so downstream mutation cannot corrupt the module-level dict.
        return dict(_LIGHT_TOKENS)  # type: ignore[return-value]
    if theme == "dark":
        return dict(_DARK_TOKENS)  # type: ignore[return-value]
    raise ValueError(f"Unknown theme: {theme!r} (expected 'light' or 'dark')")


# ---------------------------------------------------------------------------
# Scene 4b canonical term list — consumed verbatim by sf-02/03/04 tests.
# ---------------------------------------------------------------------------
# Order + exact wording are part of the contract. DO NOT paraphrase or resort.
# Referenced from docs/advisory/2026-04-17-bellmark-positioning-delivery/
# deliverables/scene4b-memo.md §B.1 + §B.4.
SCENE_4B_REQUIRED_TERMS: tuple[str, ...] = (
    "Wilson 95% CI",
    "Bootstrap",
    "Wilcoxon signed-rank",
    "Holm-Bonferroni",
    "Cohen's d",
    "Position bias",
    "Length bias",
    "Self-preference",
    "Verbosity bias",
)


# ---------------------------------------------------------------------------
# Unicode sanitizers
# ---------------------------------------------------------------------------
# XML 1.0 Char production: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] |
# [#x10000-#x10FFFF].
_XML_INVALID_RE = re.compile(
    r"[^\u0009\u000A\u000D\u0020-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]"
)
# DejaVuSans (bundled by sf-03) covers Latin + General Punctuation + limited
# supplemental. Emoji, CJK, ideographs, and astral-plane glyphs are replaced
# with "?" in the PDF-only sanitizer.
_PDF_UNSUPPORTED_RE = re.compile(r"[^\u0000-\u2FFF]")


def sanitize_text(s: str | None, *, max_len: int | None = None) -> str:
    """Lossless sanitizer used by HTML and PPTX exports.

    NFC-normalizes the input, strips XML-invalid control characters (which
    python-pptx / browsers reject), and optionally truncates to ``max_len``
    grapheme code points with a trailing ellipsis. Emoji, CJK ideographs, and
    all other BMP/astral-plane characters are PRESERVED.
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFC", str(s))
    s = _XML_INVALID_RE.sub("", s)
    if max_len is not None and len(s) > max_len:
        s = s[: max_len - 1] + "\u2026"
    return s


def sanitize_text_for_pdf(s: str | None, *, max_len: int | None = None) -> str:
    """Lossy sanitizer used by the PDF export.

    Applies :func:`sanitize_text`, then replaces every code point outside the
    DejaVuSans-covered window ``[\u0000-\u2FFF]`` with a literal ``"?"``.
    Emoji / CJK / astral-plane characters are downgraded — an accepted cosmetic
    loss for print / archival PDF. Statistical methodology text and numeric
    data are pure ASCII and unaffected.
    """
    s = sanitize_text(s, max_len=max_len)
    return _PDF_UNSUPPORTED_RE.sub("?", s)


# ---------------------------------------------------------------------------
# Reasoning-model detection helper
# ---------------------------------------------------------------------------
def is_reasoning_model(
    entity: dict,
    snapshots: list | None = None,
) -> bool:
    """Return True iff the model/judge dict should render the reasoning marker.

    Priority (shared by HTML/PDF/PPTX per design §2):
      1. If ``snapshots`` contains an entry whose ``id`` matches
         ``entity["id"]`` (or ``entity.get("model_preset_id")``) and that entry
         has ``"is_reasoning": True``.
      2. Else, if the entity's ``name`` contains the substring ``"[Reasoning"``
         (case-sensitive — mirrors the current display-name convention).
      3. Else False.
    """
    if not isinstance(entity, dict):
        return False

    entity_id = entity.get("id")
    if entity_id is None:
        entity_id = entity.get("model_preset_id")

    if snapshots and entity_id is not None:
        for snap in snapshots:
            if not isinstance(snap, dict):
                continue
            snap_id = snap.get("id")
            if snap_id is None:
                snap_id = snap.get("model_preset_id")
            if snap_id == entity_id and snap.get("is_reasoning") is True:
                return True

    name = entity.get("name", "")
    if isinstance(name, str) and "[Reasoning" in name:
        return True

    return False


__all__ = [
    "ThemeName",
    "BrandTokens",
    "COLOR_TOKEN_ALLOWLIST",
    "FRONTEND_BRAND",
    "brand",
    "get_tokens",
    "oklch_to_rgb",
    "alpha_composite",
    "token_hex",
    "_fmt_latency_ms",
    "SCENE_4B_REQUIRED_TERMS",
    "sanitize_text",
    "sanitize_text_for_pdf",
    "is_reasoning_model",
]
