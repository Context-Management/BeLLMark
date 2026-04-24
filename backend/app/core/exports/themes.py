"""Legacy theme shim — preserves the pre-sf-01 public API.

The real source of truth for export styling is now
:mod:`app.core.exports.brand_tokens`. This module keeps the old public
symbols (``get_theme``, ``FONT``, ``score_color_for_theme``,
``score_text_color_for_theme``, ``ThemeName``) importable so that
``pdf_export.py`` and ``pptx_export.py`` continue to compile untouched while
sf-02/03/04 land.

Every key consumed today by the legacy exports (grep
``backend/app/core/exports/pdf_export.py`` + ``pptx_export.py`` for
``t[…]``) is still present in the returned dict. Colour helpers
``score_color_for_theme`` / ``score_text_color_for_theme`` retain their
existing HSV logic byte-for-byte because the new tokens do not expose the
equivalent ramp.
"""

from __future__ import annotations

import colorsys

from app.core.exports.brand_tokens import ThemeName

__all__ = [
    "ThemeName",
    "FONT",
    "get_theme",
    "score_color_for_theme",
    "score_text_color_for_theme",
]


# Typography scale (shared across themes) — unchanged from pre-sf-01.
FONT = {
    "title": 28,
    "section": 18,
    "subsection": 14,
    "body": 11,
    "caption": 9,
    "table_header": 10,
    "table_cell": 9,
    "footer": 8,
}


# Legacy palettes — kept verbatim so existing exports continue to render the
# same colours during transition. Every key below is referenced from
# pdf_export.py or pptx_export.py as ``t["<key>"]``. Do not remove any.
THEMES: dict[str, dict[str, tuple[int, int, int]]] = {
    "light": {
        "bg": (255, 255, 255),
        "card_bg": (245, 247, 250),
        "accent_bg": (235, 240, 245),
        "text": (27, 42, 74),
        "text_secondary": (90, 107, 133),
        "brand": (11, 83, 148),
        "accent": (14, 165, 233),
        "success": (5, 150, 105),
        "divider": (209, 217, 230),
        "table_alt_row": (249, 250, 252),
        "table_header_bg": (235, 240, 248),
        "winner_border": (5, 150, 105),
        "callout_bg": (240, 245, 250),
        "strength_color": (5, 150, 105),
        "weakness_color": (220, 38, 38),
    },
    "dark": {
        "bg": (18, 24, 41),
        "card_bg": (26, 35, 64),
        "accent_bg": (15, 52, 96),
        "text": (240, 242, 245),
        "text_secondary": (138, 150, 170),
        "brand": (74, 222, 128),
        "accent": (56, 189, 248),
        "success": (74, 222, 128),
        "divider": (42, 53, 85),
        "table_alt_row": (22, 30, 52),
        "table_header_bg": (22, 33, 62),
        "winner_border": (74, 222, 128),
        "callout_bg": (22, 33, 62),
        "strength_color": (74, 222, 128),
        "weakness_color": (248, 113, 113),
    },
}


def get_theme(name: ThemeName = "light") -> dict:
    """Return the legacy theme palette dict for ``name``.

    Every key consumed by the pre-sf-01 ``pdf_export.py`` / ``pptx_export.py``
    is preserved. sf-02/03/04 rewrites will migrate callers to
    :func:`app.core.exports.brand_tokens.get_tokens`; until then this shim
    keeps the old sites alive.
    """
    return dict(THEMES[name])


def score_color_for_theme(
    score: float,
    theme_name: ThemeName = "light",
) -> tuple[int, int, int]:
    """HSV-ramped score colour (0..10) — unchanged from the pre-sf-01 module."""
    score = max(0.0, min(10.0, score))

    if score <= 5:
        hue = score * 12  # 0–5 → 0°–60° (red → yellow)
    else:
        hue = 60 + (score - 5) * 12  # 5–10 → 60°–120° (yellow → green)

    if theme_name == "light":
        sat = 0.55
        val = 0.90
    else:
        sat = 0.70
        val = 0.85

    r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))


def score_text_color_for_theme(
    score: float,
    theme_name: ThemeName = "light",
) -> tuple[int, int, int]:
    """Text colour for score badges — unchanged from the pre-sf-01 module."""
    if theme_name == "dark":
        return (255, 255, 255)

    score = max(0.0, min(10.0, score))
    if score <= 5:
        hue = score * 12
    else:
        hue = 60 + (score - 5) * 12

    sat = 0.8
    val = 0.55

    r, g, b = colorsys.hsv_to_rgb(hue / 360.0, sat, val)
    return (int(r * 255), int(g * 255), int(b * 255))
