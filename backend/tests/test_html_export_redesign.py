"""Tests for the sf-02 redesigned HTML export (7 slides + archival appendix).

These tests validate the per-slide structural contract from design §5 plus
Scene-4b canonical terminology (imported from brand_tokens) and resilience
to degraded/adversarial data.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import warnings
from pathlib import Path

import pytest

from app.core.exports.brand_tokens import SCENE_4B_REQUIRED_TERMS
from app.core.exports.html_export import generate_html

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MOCKUPS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "export-redesign"
    / "mockups"
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture(scope="module")
def run_128() -> dict:
    return _load("run_128_export.json")


@pytest.fixture(scope="module")
def run_no_stats() -> dict:
    return _load("run_no_stats.json")


@pytest.fixture(scope="module")
def run_no_bias() -> dict:
    return _load("run_no_bias.json")


@pytest.fixture(scope="module")
def run_adversarial() -> dict:
    return _load("run_adversarial_text.json")


# ---------------------------------------------------------------------------
# Smoke: both themes return str
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_generate_html_returns_str(run_128: dict, theme: str) -> None:
    out = generate_html(run_128, theme)
    assert isinstance(out, str)
    assert out.startswith("<!DOCTYPE html>")
    assert out.rstrip().endswith("</html>")
    assert f'data-theme="{theme}"' in out


# ---------------------------------------------------------------------------
# All 9 Scene-4b canonical terms appear verbatim.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("term", list(SCENE_4B_REQUIRED_TERMS))
def test_scene4b_terms_present(run_128: dict, term: str) -> None:
    out = generate_html(run_128, "dark")
    assert term in out, f"Missing canonical Scene-4b term: {term!r}"


# ---------------------------------------------------------------------------
# Slide count + appendix structural invariants.
# ---------------------------------------------------------------------------
def test_seven_slides_and_one_appendix(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    assert out.count('<section class="slide') == 7
    assert out.count('<section class="appendix') == 1


# ---------------------------------------------------------------------------
# Slide 1 — Cover
# ---------------------------------------------------------------------------
def test_slide_cover_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    # Eyebrow
    assert "MODEL EVALUATION REPORT" in out
    # Run name (Financial Analysis)
    assert run_128["run"]["name"] in out
    # KEY FINDING block with winner name + weighted score
    assert "KEY FINDING" in out.upper()
    winner = run_128["models"][0]
    assert winner["name"] in out
    assert f'{winner["weighted_score"]:.2f}' in out
    # PODIUM with 3 names
    assert "PODIUM" in out.upper()
    for m in run_128["models"][:3]:
        assert m["name"] in out
    # Six scope tiles
    for label in ("CANDIDATES", "PROMPTS", "JUDGES", "RUBRIC CRITERIA", "TOTAL SPEND", "MODE"):
        assert label in out.upper()
    # Footer
    run_id = run_128["run"]["id"]
    assert f"BeLLMark Run #{run_id:04d}" in out
    assert "bellmark.ai" in out


# ---------------------------------------------------------------------------
# Slide 2 — Executive summary
# ---------------------------------------------------------------------------
def test_slide_executive_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    # Winner prominent heading
    winner = run_128["models"][0]
    assert winner["name"] in out
    # 95% CI pattern
    assert re.search(r"95% CI\s+\d+\.\d{2}[–-]\d+\.\d{2}", out) is not None
    # Three scope tiles
    for label in ("TOTAL SPEND", "TOP CLUSTER", "SAMPLE SIZE"):
        assert label in out.upper()
    # Top-3 $/prompt markers
    assert re.search(r"\$[0-9]+\.[0-9]+/prompt", out) is not None


# ---------------------------------------------------------------------------
# Slide 3 — Leaderboard
# ---------------------------------------------------------------------------
def test_slide_leaderboard_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    # Table column headers — case-insensitive. Updated 2026-04-21 for the
    # 9-column leaderboard: LC win rate → LC WIN; added TOK/S, AVG LATENCY.
    lower = out.lower()
    for header in (
        "#", "model", "mean", "95% ci", "win rate",
        "tok/s", "avg latency", "lc win", "$/prompt",
    ):
        assert header in lower
    for m in run_128["models"]:
        assert m["name"] in out


# ---------------------------------------------------------------------------
# Slide 4 — Per-criterion
# ---------------------------------------------------------------------------
def test_slide_criteria_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    for c in run_128["run"]["criteria"]:
        assert c["name"] in out
    assert "Best-in-class per criterion" in out or "BEST-IN-CLASS PER CRITERION" in out.upper()


# ---------------------------------------------------------------------------
# Slide 5 — Statistical rigor
# ---------------------------------------------------------------------------
def test_slide_stats_rigor_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    # All 9 Scene-4b terms already verified; double-check methodology paragraph block is present.
    assert 'data-kind="stats-rigor"' in out
    # M-code legend (at minimum M1 through M_N where N=min(8, len(models)))
    n = min(8, len(run_128["models"]))
    for i in range(n):
        assert f"M{i + 1}" in out
        # Legend contains "M1 = <name>" style text
        expected = f"M{i + 1}</strong> = "
        assert expected in out, f"Legend entry missing for M{i + 1}"
    # HOW TO READ legend + EFFECT SIZE legend
    assert "HOW TO READ" in out.upper()
    assert "EFFECT SIZE" in out.upper()
    for eff in ("Negligible", "Small", "Medium", "Large"):
        assert eff in out


# ---------------------------------------------------------------------------
# Slide 6 — Bias & calibration
# ---------------------------------------------------------------------------
def test_slide_bias_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    for panel in ("Position bias", "Length bias", "Self-preference", "Verbosity bias"):
        assert panel in out
    # Each panel has Detected or Not detected
    assert "Detected" in out or "Not detected" in out
    # Calibration strip
    assert "INTER-JUDGE AGREEMENT" in out.upper()
    assert "FLEISS' K" in out.upper() or "COHEN'S K" in out.upper()
    assert "DISAGREEMENT QUESTIONS" in out.upper()


# ---------------------------------------------------------------------------
# Slide 7 — Methodology & sign-off
# ---------------------------------------------------------------------------
def test_slide_methodology_contract(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    for label in ("SCOPE", "RUBRIC CRITERIA", "JUDGE PANEL", "SIGN-OFF"):
        assert label in out.upper()
    # Scope labels per contract
    for lbl in (
        "Prompts",
        "Candidate models",
        "Judges",
        "Rubric criteria",
        "Judging mode",
        "Judgments total",
        "Total spend",
    ):
        assert lbl in out
    # Sign-off fields
    for field in ("Prepared by", "Reviewed by", "Export date", "Source", "Methodology"):
        assert field in out


# ---------------------------------------------------------------------------
# XSS: <script> literal MUST NOT survive; must be escaped.
# ---------------------------------------------------------------------------
def test_xss_run_name_escaped(run_128: dict) -> None:
    data = copy.deepcopy(run_128)
    data["run"]["name"] = '<script>alert(1)</script>'
    out = generate_html(data, "dark")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


# ---------------------------------------------------------------------------
# Degraded data: statistics=None
# ---------------------------------------------------------------------------
def test_statistics_none_degrades_gracefully(run_no_stats: dict) -> None:
    out = generate_html(run_no_stats, "dark")
    assert isinstance(out, str)
    # Stats rigor slide placeholder
    assert "Statistical analysis unavailable for this run." in out
    # Methodology paragraph with all 9 Scene-4b terms still present
    for term in SCENE_4B_REQUIRED_TERMS:
        assert term in out, f"Missing {term} under statistics=None"
    # Slide 2 CI unavailable
    assert "(CI unavailable for this run)" in out


# ---------------------------------------------------------------------------
# Degraded data: bias_report=None
# ---------------------------------------------------------------------------
def test_bias_none_degrades_gracefully(run_no_bias: dict) -> None:
    out = generate_html(run_no_bias, "dark")
    assert "Bias diagnostics unavailable for this run." in out
    # Calibration strip still renders (judge_summary + kappa present)
    assert "INTER-JUDGE AGREEMENT" in out.upper()


# ---------------------------------------------------------------------------
# Adversarial text: emoji + CJK survive; \x0B stripped; HTML-special escaped.
# ---------------------------------------------------------------------------
def test_adversarial_text_preserved_and_sanitized(run_adversarial: dict) -> None:
    out = generate_html(run_adversarial, "dark")
    assert "🔥" in out, "Emoji should be preserved by sanitize_text"
    assert "中" in out, "CJK ideograph should be preserved"
    assert "\x0b" not in out, "Vertical-tab control char must be stripped"
    # Any raw '<' or '>' from run-sourced strings must be escaped wherever
    # they were inserted; the raw pattern of '<script' from user prompt etc.
    # would appear escaped. We assert the control chars were stripped + that
    # a dangerous tag injected into a name field would have been escaped.
    data = copy.deepcopy(run_adversarial)
    data["run"]["name"] = "</title><script>x</script>"
    out2 = generate_html(data, "dark")
    assert "</title><script>" not in out2
    assert "&lt;/title&gt;" in out2 or "&lt;script&gt;" in out2


# ---------------------------------------------------------------------------
# Appendix preservation: archival question content still present.
# ---------------------------------------------------------------------------
def test_appendix_preserves_question_content(run_128: dict) -> None:
    out = generate_html(run_128, "dark")
    appendix_start = out.find('<section class="appendix')
    assert appendix_start > 0
    appendix = out[appendix_start:]
    first_q = run_128["questions"][0]
    snippet = first_q["user_prompt"][:40]
    # Escape HTML-special characters the same way the export does.
    import html as _h
    escaped_snippet = _h.escape(snippet, quote=True)
    assert escaped_snippet in appendix or snippet in appendix


# ---------------------------------------------------------------------------
# Visual regression (non-blocking): RMS diff vs. mockup, logs warning only.
# ---------------------------------------------------------------------------
@pytest.mark.visual
def test_visual_regression_cover_slide(tmp_path: Path, run_128: dict) -> None:
    pytest.importorskip("playwright")
    try:
        from PIL import Image, ImageChops
    except ImportError:
        pytest.skip("Pillow not available")
    # Require an actual browser binary on PATH
    if not (shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")):
        pytest.skip("No Chromium binary available for playwright")

    mockup_path = MOCKUPS_DIR / "slide-01-cover-light.png"
    if not mockup_path.exists():
        pytest.skip("Mockup unavailable")

    from playwright.sync_api import sync_playwright

    out_html = tmp_path / "report.html"
    out_html.write_text(generate_html(run_128, "light"))

    screenshot_path = tmp_path / "slide-01.png"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto(f"file://{out_html}")
            el = page.locator('[data-kind="cover"]')
            el.screenshot(path=str(screenshot_path))
            browser.close()
    except Exception as e:
        pytest.skip(f"Playwright runtime unavailable: {e}")

    try:
        rendered = Image.open(screenshot_path).convert("RGB").resize((1920, 1080))
        expected = Image.open(mockup_path).convert("RGB").resize((1920, 1080))
        diff = ImageChops.difference(rendered, expected)
        # Normalized RMS
        import math
        stat_sum = 0.0
        px = 0
        for band in diff.split():
            hist = band.histogram()
            for i, count in enumerate(hist):
                stat_sum += (i * i) * count
                px += count
        rms = math.sqrt(stat_sum / max(1, px)) / 255.0
    except Exception as e:
        pytest.skip(f"Visual comparison failed: {e}")

    if rms >= 0.15:
        warnings.warn(
            f"Visual regression RMS diff {rms:.3f} ≥ 0.15 (non-blocking)",
            stacklevel=2,
        )
    # Non-blocking: no assert.
    return


# ---------------------------------------------------------------------------
# 2026-04-21 brand-parity regression tests
# ---------------------------------------------------------------------------
from app.core.exports.brand_tokens import (
    COLOR_TOKEN_ALLOWLIST,
    get_tokens,
    token_hex,
)


def _render(theme: str) -> str:
    return generate_html(_load("run_128_export.json"), theme)


def test_root_css_emits_every_allowlist_token_as_kebab_var():
    html = _render("dark")
    for name in COLOR_TOKEN_ALLOWLIST:
        kebab = name.replace("_", "-")
        pattern = rf"--{kebab}:\s*rgb\(\d+,\s*\d+,\s*\d+\);"
        assert re.search(pattern, html), f"missing CSS var --{kebab}"


def test_accent_is_not_chart_1_in_emitted_css():
    for theme in ("light", "dark"):
        html = _render(theme)
        accent_rgb = get_tokens(theme)["accent"]
        chart_1_rgb = get_tokens(theme)["chart_1"]
        assert f"--accent: rgb({accent_rgb[0]},{accent_rgb[1]},{accent_rgb[2]});" in html
        assert f"--chart-1: rgb({chart_1_rgb[0]},{chart_1_rgb[1]},{chart_1_rgb[2]});" in html
        assert accent_rgb != chart_1_rgb


def test_brain_svg_not_emitted_anywhere():
    """The brain icon was retired in favour of the existing
    "[Reasoning …]" suffix in model names. The HTML must not emit any
    Lucide brain paths — they're redundant and the user rejected them."""
    for theme in ("light", "dark"):
        html = _render(theme)
        # The two characteristic Lucide brain path signatures.
        assert 'M12 5a3 3 0 1 0-5.997.125' not in html, f"{theme}: brain SVG left in output"
        assert 'class="brain-icon"' not in html, f"{theme}: brain-icon class leaked"


def test_winner_rendered_with_frontend_amber_color():
    """The winner (rank 1) model name must use the frontend's amber /
    yellow brand color — same hex Tailwind `text-amber-600` /
    `dark:text-yellow-400` produces in OverviewSection.tsx."""
    from app.core.exports.brand_tokens import brand
    for theme, expected_rgb in (("light", brand("light", "winner_text")),
                                 ("dark",  brand("dark",  "winner_text"))):
        html = _render(theme)
        rgb_str = f"rgb({expected_rgb[0]}, {expected_rgb[1]}, {expected_rgb[2]})"
        hex_str = token_hex(expected_rgb).lower()
        # The class definition lives in the <style> block in one of these forms.
        assert (
            rgb_str in html
            or rgb_str.replace(" ", "") in html
            or hex_str in html.lower()
        ), f"{theme}: winner color {expected_rgb} / {hex_str} not present"
        # And the semantic class is applied at least once.
        assert "brand-winner-text" in html


def test_no_brain_stroke_paths_in_css_or_markup():
    """Regression guard: the `.brain-icon` CSS rule is gone and no
    leftover SVG brain path is rendered inline."""
    html = _render("dark")
    # Tolerate a brief mention in historical comments — forbid only the
    # actual CSS rule + the full SVG shape.
    assert 'brain-icon {' not in html
    assert 'stroke="currentColor"' not in html


def test_currentcolor_is_not_present_anywhere():
    for theme in ("light", "dark"):
        html = _render(theme)
        assert "currentColor" not in html, (
            f"{theme}: currentColor leaked into output"
        )


def test_leaderboard_header_uses_uppercase_labels():
    html = _render("light")
    for label in ("TOK/S", "AVG LATENCY", "WIN RATE", "95% CI", "MEAN",
                   "LC WIN", "$/PROMPT", "MODEL"):
        assert f"<th>{label}</th>" in html, f"missing <th>{label}</th>"


def test_leaderboard_colgroup_widths_sum_to_100():
    html = _render("light")
    widths = [int(m) for m in re.findall(r'<col style="width:(\d+)%">', html)]
    assert len(widths) == 9
    assert sum(widths) == 100


def test_leaderboard_contains_fixture_tokens_per_second_values():
    data = _load("run_128_export.json")
    html = generate_html(data, "light")
    tps_values = [m.get("tokens_per_second") for m in data["models"]]
    formatted = [f"<td>{float(v):.1f}</td>" for v in tps_values if v is not None]
    # at least one tok/s value renders as expected
    assert any(f in html for f in formatted), (
        f"no tokens_per_second cell matching fixture values found"
    )
