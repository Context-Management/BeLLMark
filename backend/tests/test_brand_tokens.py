"""Unit tests for :mod:`app.core.exports.brand_tokens`.

Covers:
  (a) OKLCH→sRGB accuracy on known reference vectors (± 2 per channel)
  (b) Both theme dicts are fully populated with expected key set + int tuples
  (c) SCENE_4B_REQUIRED_TERMS: exactly 9 canonical strings, tuple immutable
  (d) Legacy themes.py shim still exposes every key consumed by pdf_export.py
      and pptx_export.py (prevents sf-02/03/04 transition regressions)
  (e) sanitize_text / sanitize_text_for_pdf behaviour
  (f) is_reasoning_model priority chain
  (g) alpha_composite correctness
"""

from __future__ import annotations

from app.core.exports import brand_tokens as bt
from app.core.exports import themes as legacy_themes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TOLERANCE = 2  # ± per channel, per design §6 risk table


def _within(actual: tuple[int, int, int], expected: tuple[int, int, int]) -> bool:
    return all(abs(a - e) <= TOLERANCE for a, e in zip(actual, expected))


# Every BrandTokens key (mirrors TypedDict) — updated here if schema grows.
# After the 2026-04-21 brand-parity refactor, color tokens mirror the full
# frontend color allowlist; see `brand_tokens.COLOR_TOKEN_ALLOWLIST`.
_BRAND_TOKEN_COLOR_KEYS = set(bt.COLOR_TOKEN_ALLOWLIST)
_BRAND_TOKEN_NUMERIC_KEYS = {
    "radius_sm",
    "radius_md",
    "radius_lg",
    "font_title",
    "font_h2",
    "font_body",
    "font_caption",
    "font_footer",
}
_ALL_TOKEN_KEYS = _BRAND_TOKEN_COLOR_KEYS | _BRAND_TOKEN_NUMERIC_KEYS


# ---------------------------------------------------------------------------
# (a) OKLCH→sRGB accuracy
# ---------------------------------------------------------------------------


def test_oklch_pure_white() -> None:
    assert _within(bt.oklch_to_rgb(1.0, 0.0, 0.0), (255, 255, 255))


def test_oklch_pure_black() -> None:
    assert _within(bt.oklch_to_rgb(0.0, 0.0, 0.0), (0, 0, 0))


def test_oklch_foreground_light_reference_gray() -> None:
    # oklch(0.145 0 0) — frontend --foreground light. CSS Color 4 / oklch.com
    # reference gives sRGB (10, 10, 10). Any correct OKLCH→sRGB converter
    # MUST land within ±2 of (10, 10, 10). Note: earlier internal design-doc
    # draft incorrectly claimed (36, 36, 36); keeping the mathematically-
    # correct target here to avoid baking in a broken converter.
    assert _within(bt.oklch_to_rgb(0.145, 0.0, 0.0), (10, 10, 10))


def test_oklch_985_light_gray() -> None:
    # oklch(0.985 0 0) — used by --primary-foreground light, --foreground dark.
    assert _within(bt.oklch_to_rgb(0.985, 0.0, 0.0), (250, 250, 250))


def test_oklch_922_light_border() -> None:
    # oklch(0.922 0 0) — --border light.
    assert _within(bt.oklch_to_rgb(0.922, 0.0, 0.0), (229, 229, 229))


def test_oklch_chart_1_light_warm_orange() -> None:
    # oklch(0.646 0.222 41.116) — chart-1 light (warm orange). Ground truth
    # from oklch.com: approx (245, 73, 0).
    result = bt.oklch_to_rgb(0.646, 0.222, 41.116)
    assert _within(result, (245, 73, 0)), f"got {result}"


def test_oklch_destructive_light_red() -> None:
    # oklch(0.577 0.245 27.325) — --destructive light. Ground truth ≈
    # (231, 0, 11).
    result = bt.oklch_to_rgb(0.577, 0.245, 27.325)
    assert _within(result, (231, 0, 11)), f"got {result}"


# ---------------------------------------------------------------------------
# (b) theme dicts fully populated
# ---------------------------------------------------------------------------


def test_light_tokens_shape() -> None:
    tokens = bt.get_tokens("light")
    assert set(tokens.keys()) == _ALL_TOKEN_KEYS
    for key in _BRAND_TOKEN_COLOR_KEYS:
        value = tokens[key]
        assert isinstance(value, tuple), f"{key} not a tuple"
        assert len(value) == 3
        for channel in value:
            assert isinstance(channel, int), f"{key} channel not int: {value}"
            assert 0 <= channel <= 255
    for key in _BRAND_TOKEN_NUMERIC_KEYS:
        assert isinstance(tokens[key], (int, float))


def test_dark_tokens_shape() -> None:
    tokens = bt.get_tokens("dark")
    assert set(tokens.keys()) == _ALL_TOKEN_KEYS
    for key in _BRAND_TOKEN_COLOR_KEYS:
        value = tokens[key]
        assert isinstance(value, tuple)
        assert len(value) == 3
        for channel in value:
            assert isinstance(channel, int)
            assert 0 <= channel <= 255


def test_light_background_is_stone_100() -> None:
    """Layout.tsx uses bg-stone-100 (#F5F5F4), NOT shadcn's pure white."""
    assert bt.get_tokens("light")["background"] == (0xF5, 0xF5, 0xF4)


def test_dark_background_is_gray_900() -> None:
    """Layout.tsx uses bg-gray-900 (#111827 — dark navy), NOT pure charcoal."""
    assert bt.get_tokens("dark")["background"] == (0x11, 0x18, 0x27)


def test_get_tokens_returns_independent_copies() -> None:
    original = bt.get_tokens("light")["background"]
    a = bt.get_tokens("light")
    a["background"] = (1, 2, 3)  # type: ignore[typeddict-item]
    b = bt.get_tokens("light")
    assert b["background"] == original, "mutation leaked into module state"


# ---------------------------------------------------------------------------
# (c) Scene 4b canonical tuple
# ---------------------------------------------------------------------------


def test_scene_4b_terms_has_exactly_nine_items() -> None:
    assert len(bt.SCENE_4B_REQUIRED_TERMS) == 9


def test_scene_4b_terms_is_immutable_tuple() -> None:
    assert isinstance(bt.SCENE_4B_REQUIRED_TERMS, tuple)


def test_scene_4b_terms_contains_expected_literals() -> None:
    expected = {
        "Wilson 95% CI",
        "Bootstrap",
        "Wilcoxon signed-rank",
        "Holm-Bonferroni",
        "Cohen's d",
        "Position bias",
        "Length bias",
        "Self-preference",
        "Verbosity bias",
    }
    assert set(bt.SCENE_4B_REQUIRED_TERMS) == expected


# ---------------------------------------------------------------------------
# (d) legacy themes.py shim preserves every key consumed today
# ---------------------------------------------------------------------------


_LEGACY_THEME_KEYS = {
    "bg",
    "card_bg",
    "accent_bg",
    "text",
    "text_secondary",
    "brand",
    "accent",
    "success",
    "divider",
    "table_alt_row",
    "table_header_bg",
    "winner_border",
    "callout_bg",
    "strength_color",
    "weakness_color",
}


def test_legacy_get_theme_light_preserves_all_keys() -> None:
    theme = legacy_themes.get_theme("light")
    for key in _LEGACY_THEME_KEYS:
        assert key in theme, f"legacy shim missing {key!r}"
        v = theme[key]
        assert isinstance(v, tuple) and len(v) == 3


def test_legacy_get_theme_dark_preserves_all_keys() -> None:
    theme = legacy_themes.get_theme("dark")
    for key in _LEGACY_THEME_KEYS:
        assert key in theme, f"legacy shim missing {key!r}"


def test_legacy_font_still_exported() -> None:
    # pdf_export + pptx_export read FONT["title"], FONT["body"], etc.
    for key in ("title", "section", "subsection", "body", "caption",
                "table_header", "table_cell", "footer"):
        assert key in legacy_themes.FONT


def test_legacy_score_color_helpers_still_work() -> None:
    # Smoke: signatures and output shape match pre-sf-01 behaviour.
    r, g, b = legacy_themes.score_color_for_theme(7.5, "light")
    assert 0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255
    r2, g2, b2 = legacy_themes.score_text_color_for_theme(7.5, "dark")
    assert (r2, g2, b2) == (255, 255, 255)


# ---------------------------------------------------------------------------
# (e) sanitizers
# ---------------------------------------------------------------------------


def test_sanitize_text_removes_xml_invalid_control_char() -> None:
    assert bt.sanitize_text("a\x0Bb") == "ab"


def test_sanitize_text_preserves_emoji_and_cjk() -> None:
    # Emoji (U+1F525 🔥) and CJK (中文) both survive the lossless sanitizer.
    out = bt.sanitize_text("\U0001F525\u4E2D\u6587")
    assert out == "\U0001F525\u4E2D\u6587"


def test_sanitize_text_handles_none() -> None:
    assert bt.sanitize_text(None) == ""


def test_sanitize_text_truncates_with_ellipsis_when_max_len_set() -> None:
    # 5-char cap on a 10-char string: last char replaced by ellipsis (… = U+2026).
    out = bt.sanitize_text("abcdefghij", max_len=5)
    assert len(out) == 5
    assert out.endswith("\u2026")


def test_sanitize_text_nfc_normalizes() -> None:
    # 'é' via combining acute ↔ precomposed.
    combined = "e\u0301"
    assert bt.sanitize_text(combined) == "\u00e9"


def test_sanitize_text_for_pdf_replaces_emoji_with_question_mark() -> None:
    # 🔥 (U+1F525) is outside the DejaVu BMP-subset window → "?"
    assert bt.sanitize_text_for_pdf("a\U0001F525b") == "a?b"


def test_sanitize_text_for_pdf_replaces_cjk_with_question_mark() -> None:
    # CJK "中文" both fall outside [\u0000-\u2FFF]
    assert bt.sanitize_text_for_pdf("\U0001F525\u4E2D\u6587") == "???"


def test_sanitize_text_for_pdf_preserves_curly_quotes_and_em_dash() -> None:
    # “ (U+201C), ” (U+201D), ‘ (U+2018), ’ (U+2019), — (U+2014) all fall
    # inside [\u0000-\u2FFF] → preserved.
    out = bt.sanitize_text_for_pdf("a\u201cb\u201d\u2014c")
    assert out == "a\u201cb\u201d\u2014c"


# ---------------------------------------------------------------------------
# (f) is_reasoning_model
# ---------------------------------------------------------------------------


def test_is_reasoning_model_from_snapshot_flag() -> None:
    entity = {"id": 1, "name": "Foo"}
    snapshots = [{"id": 1, "is_reasoning": True}]
    assert bt.is_reasoning_model(entity, snapshots=snapshots) is True


def test_is_reasoning_model_snapshot_missing_defaults_to_name_check() -> None:
    # snapshot has the wrong id → fall through to name check.
    entity = {"id": 2, "name": "Claude Opus 4.6 [Reasoning (high)]"}
    snapshots = [{"id": 99, "is_reasoning": True}]
    assert bt.is_reasoning_model(entity, snapshots=snapshots) is True


def test_is_reasoning_model_from_name_substring() -> None:
    assert bt.is_reasoning_model({"name": "Claude Opus 4.6 [Reasoning (high)]"}) is True


def test_is_reasoning_model_false_for_plain_name() -> None:
    assert bt.is_reasoning_model({"name": "GPT-5.4"}) is False


def test_is_reasoning_model_handles_empty_snapshot_list() -> None:
    assert bt.is_reasoning_model({"id": 1, "name": "Plain"}, snapshots=[]) is False


def test_is_reasoning_model_is_case_sensitive_on_name() -> None:
    # Priority (2) says case-sensitive "[Reasoning" substring.
    assert bt.is_reasoning_model({"name": "model [reasoning]"}) is False


# ---------------------------------------------------------------------------
# (g) alpha_composite
# ---------------------------------------------------------------------------


def test_alpha_composite_white_over_dark_gray_at_10_percent() -> None:
    # Canonical spec example: (255,255,255) at 10% over (37,37,37) → (59,59,59).
    result = bt.alpha_composite((255, 255, 255), (37, 37, 37), 0.1)
    assert all(abs(c - 59) <= 1 for c in result), f"got {result}"


def test_alpha_composite_zero_alpha_returns_bottom() -> None:
    assert bt.alpha_composite((255, 255, 255), (10, 20, 30), 0.0) == (10, 20, 30)


def test_alpha_composite_full_alpha_returns_top() -> None:
    assert bt.alpha_composite((255, 255, 255), (10, 20, 30), 1.0) == (255, 255, 255)


# ---------------------------------------------------------------------------
# (h) New 2026-04-21 additions — allowlist + token_hex + _fmt_latency_ms
# ---------------------------------------------------------------------------


def test_color_token_allowlist_length() -> None:
    assert len(bt.COLOR_TOKEN_ALLOWLIST) == 23


def test_color_token_allowlist_names_are_unique() -> None:
    assert len(set(bt.COLOR_TOKEN_ALLOWLIST)) == len(bt.COLOR_TOKEN_ALLOWLIST)


def test_every_allowlist_name_has_annotation_and_value() -> None:
    for theme in ("light", "dark"):
        tokens = bt.get_tokens(theme)  # type: ignore[arg-type]
        for name in bt.COLOR_TOKEN_ALLOWLIST:
            assert name in bt.BrandTokens.__annotations__, (
                f"{name} missing from BrandTokens.__annotations__"
            )
            assert name in tokens, f"{name} missing from get_tokens('{theme}')"
            value = tokens[name]  # type: ignore[literal-required]
            assert isinstance(value, tuple) and len(value) == 3, value
            for channel in value:
                assert isinstance(channel, int), channel
                assert 0 <= channel <= 255, channel


def test_accent_not_aliased_to_chart_1() -> None:
    for theme in ("light", "dark"):
        tokens = bt.get_tokens(theme)  # type: ignore[arg-type]
        assert tokens["accent"] != tokens["chart_1"], (
            f"{theme}: accent is aliased to chart_1"
        )


def test_accent_is_neutral_not_chart1_orange_or_blue() -> None:
    """`--accent` is a layout-neutral token (stone-200 light / gray-800
    dark), NOT the chart_1 orange/blue that earlier code aliased it to.
    The core invariant is that accent is neutral and != chart_1."""
    for theme in ("light", "dark"):
        accent = bt.get_tokens(theme)["accent"]
        chart_1 = bt.get_tokens(theme)["chart_1"]
        # accent must be chromatically near-neutral (Tailwind gray-800
        # = #1F2937 has a 24-unit spread — it's slate-tinted on purpose).
        spread = max(accent) - min(accent)
        assert spread <= 30, f"{theme}: accent {accent} is not near-neutral"
        assert accent != chart_1


def test_token_hex_round_trips_canonical_colors() -> None:
    assert bt.token_hex((0, 0, 0)) == "#000000"
    assert bt.token_hex((255, 255, 255)) == "#FFFFFF"
    assert bt.token_hex((181, 181, 181)) == "#B5B5B5"
    assert bt.token_hex((16, 32, 48)) == "#102030"


def test_fmt_latency_ms_formats() -> None:
    assert bt._fmt_latency_ms(None) == "—"
    assert bt._fmt_latency_ms(0) == "—"
    assert bt._fmt_latency_ms(-1) == "—"
    assert bt._fmt_latency_ms(500) == "500ms"
    assert bt._fmt_latency_ms(999) == "999ms"
    assert bt._fmt_latency_ms(1500) == "1.5s"
    assert bt._fmt_latency_ms(59_999) == "60.0s"
    assert bt._fmt_latency_ms(60_000) == "1m 0s"
    assert bt._fmt_latency_ms(90_000) == "1m 30s"
    assert bt._fmt_latency_ms(3_900_000) == "1h 5m"


def test_fmt_latency_ms_rejects_non_numeric() -> None:
    assert bt._fmt_latency_ms("not-a-number") == "—"  # type: ignore[arg-type]
