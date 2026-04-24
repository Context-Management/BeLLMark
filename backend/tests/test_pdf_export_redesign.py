"""sf-03 — PDF export redesign tests.

Covers:
* signature + theme variants
* 7 page structure (cover, exec, leaderboard, criteria, stats, bias, methodology)
* page-level substring assertions via pypdf text extraction
* Scene 4b canonical methodology paragraph presence (page 5)
* graceful degradation (missing statistics / bias_report)
* adversarial-text sanitisation (emoji / CJK → "?")
* optional pdftotext cross-check when the binary is available
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pypdf
import pytest

from app.core.exports.brand_tokens import SCENE_4B_REQUIRED_TERMS
from app.core.exports.pdf_export import generate_pdf

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RUN_128 = json.loads((FIXTURE_DIR / "run_128_export.json").read_text())
RUN_NO_STATS = json.loads((FIXTURE_DIR / "run_no_stats.json").read_text())
RUN_NO_BIAS = json.loads((FIXTURE_DIR / "run_no_bias.json").read_text())
RUN_ADVERSARIAL = json.loads((FIXTURE_DIR / "run_adversarial_text.json").read_text())


def _extract_pages(pdf_bytes: bytes) -> list[str]:
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    return [p.extract_text() or "" for p in reader.pages]


# ---------------------------------------------------------------------------
# 1. Signature + basic shape
# ---------------------------------------------------------------------------
def test_signature_light():
    b = generate_pdf(RUN_128, "light")
    assert isinstance(b, bytes)
    assert b.startswith(b"%PDF")
    assert len(b) < 2_000_000


def test_signature_dark():
    b = generate_pdf(RUN_128, "dark")
    assert isinstance(b, bytes)
    assert b.startswith(b"%PDF")
    assert len(b) < 2_000_000


def test_seven_pages():
    b = generate_pdf(RUN_128, "light")
    reader = pypdf.PdfReader(io.BytesIO(b))
    assert len(reader.pages) == 7


# ---------------------------------------------------------------------------
# 2. Per-page content assertions
# ---------------------------------------------------------------------------
def test_page_cover_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[0]
    assert "MODEL EVALUATION REPORT" in p
    assert RUN_128["run"]["name"] in p


def test_page_executive_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[1]
    winner_name = RUN_128["models"][0]["name"]
    assert winner_name in p or winner_name[:20] in p
    # HTML-rendered executive slide shows the score + 95% CI in the Winner
    # block. Either the compact "9.22" number or the explicit "95% CI" label
    # must be visible — both are rendered by the html_export template.
    score_str = f"{RUN_128['models'][0]['weighted_score']:.2f}"
    assert score_str in p, f"expected winner score {score_str!r} on executive page"
    assert "95% CI" in p


def test_page_leaderboard_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[2]
    # Column headers are rendered as uppercase eyebrow-style labels in the
    # html_export leaderboard slide (MEAN / 95% CI / WIN RATE / …). Match
    # case-insensitively so either casing passes.
    p_ci = p.upper()
    assert "MEAN" in p_ci
    assert "95% CI" in p_ci
    top3 = RUN_128["models"][:3]
    hits = sum(
        1 for m in top3 if m["name"] in p or m["name"][:20] in p
    )
    assert hits >= 3, f"expected top-3 model names on leaderboard page, got {hits}"


def test_page_criteria_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    # Criteria names are rendered as uppercase eyebrow-style column headers
    # AND as full-case names in the best-in-class footer. pypdf inserts
    # newlines when a name wraps across two lines in either rendering, so we
    # normalise whitespace before matching, and match case-insensitively.
    import re
    normalised = re.sub(r"\s+", " ", pages[3].upper())
    for c in RUN_128["run"]["criteria"]:
        name_ci = c["name"].upper()
        assert name_ci in normalised, (
            f"criterion {c['name']!r} missing from criteria page"
        )


def test_page_stats_contains_scene4b_terms():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[4]
    missing = [t for t in SCENE_4B_REQUIRED_TERMS if t not in p]
    assert not missing, f"Scene 4b terms missing from page 5: {missing}"


def test_page_bias_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[5]
    for label in ("Position bias", "Length bias", "Self-preference", "Verbosity bias"):
        assert label in p, f"bias panel label {label!r} missing from page 6"


def test_page_methodology_contents():
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    p = pages[6]
    assert "Prepared by" in p
    assert "Methodology" in p


# ---------------------------------------------------------------------------
# 3. Graceful degradation
# ---------------------------------------------------------------------------
def test_no_stats_fixture_still_has_scene4b_and_unavailable():
    b = generate_pdf(RUN_NO_STATS, "light")
    pages = _extract_pages(b)
    assert len(pages) == 7
    # static methodology paragraph still carries all 9 terms
    p5 = pages[4]
    missing = [t for t in SCENE_4B_REQUIRED_TERMS if t not in p5]
    assert not missing, f"Scene 4b terms missing in degraded run: {missing}"
    # "unavailable" substring present somewhere
    assert any("unavailable" in p for p in pages)


def test_no_bias_fixture_bias_page_unavailable():
    b = generate_pdf(RUN_NO_BIAS, "light")
    pages = _extract_pages(b)
    assert len(pages) == 7
    assert "unavailable" in pages[5]


# ---------------------------------------------------------------------------
# 4. Dark-theme structural parity
# ---------------------------------------------------------------------------
def test_dark_theme_page_structure():
    pages = _extract_pages(generate_pdf(RUN_128, "dark"))
    assert len(pages) == 7
    assert "MODEL EVALUATION REPORT" in pages[0]
    missing = [t for t in SCENE_4B_REQUIRED_TERMS if t not in pages[4]]
    assert not missing
    for label in ("Position bias", "Length bias", "Self-preference", "Verbosity bias"):
        assert label in pages[5]


# ---------------------------------------------------------------------------
# 5. pdftotext cross-check (optional — skipped without the binary)
# ---------------------------------------------------------------------------
@pytest.mark.pdftools
@pytest.mark.skipif(
    shutil.which("pdftotext") is None,
    reason="pdftotext not installed",
)
def test_pdftotext_roundtrip_has_scene4b_terms():
    b = generate_pdf(RUN_128, "light")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b)
        pdf_path = f.name
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            check=True,
            text=True,
        )
        text = out.stdout
    finally:
        Path(pdf_path).unlink(missing_ok=True)
    missing = [t for t in SCENE_4B_REQUIRED_TERMS if t not in text]
    assert not missing, f"Scene 4b missing from pdftotext output: {missing}"


# ---------------------------------------------------------------------------
# 6. Adversarial text — robustness under emoji / CJK / control chars.
#
# When the PDF was rendered by fpdf + bundled DejaVu, the generator
# explicitly downgraded emoji and CJK to '?' because those glyphs weren't
# in the font. The current WeasyPrint pipeline uses the HTML's full font
# stack (system sans-serif) which handles the BMP fine and preserves CJK
# / emoji losslessly — same behavior as the HTML and PPTX exports.
# Contract:
#   (a) generate_pdf must NOT raise on adversarial input
#   (b) must produce a valid PDF
#   (c) the XML-invalid \x0B control char MUST be stripped
#       (pypdf-based check — doesn't depend on `pdftotext` binary)
#   (d) emoji + CJK MUST be preserved as real text (pdftotext-gated —
#       only runs when the binary is available, because pypdf's own
#       text extractor normalises some Unicode differently)
# ---------------------------------------------------------------------------
def test_adversarial_text_sanitised():
    b = generate_pdf(RUN_ADVERSARIAL, "light")
    assert isinstance(b, bytes)
    assert b.startswith(b"%PDF")

    # (c) Control-char strip — verified via pypdf (always available).
    import pypdf
    import io as _io
    reader = pypdf.PdfReader(_io.BytesIO(b))
    pypdf_text = "".join((p.extract_text() or "") for p in reader.pages)
    assert "\x0b" not in pypdf_text, (
        "vertical-tab control char survived sanitization (pypdf check)"
    )


@pytest.mark.pdftools
def test_adversarial_text_preserves_emoji_and_cjk():
    """Positive assertion: WeasyPrint-backed PDF preserves emoji and CJK
    losslessly (previous fpdf pipeline downgraded both to '?'). This locks
    the behavioural improvement against future regressions."""
    b = generate_pdf(RUN_ADVERSARIAL, "light")

    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext not installed")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b)
        pdf_path = f.name
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", pdf_path, "-"],
            capture_output=True,
            check=True,
            text=True,
        )
        text = out.stdout
    finally:
        Path(pdf_path).unlink(missing_ok=True)

    # The adversarial fixture injects "🔥" and "中文测试" into run.name and
    # several question/judgment fields. At least one of each family must
    # survive through WeasyPrint's font pipeline into the PDF text layer.
    assert "🔥" in text, "emoji (🔥 U+1F525) not preserved in PDF text"
    assert "中" in text or "文" in text, "CJK glyphs not preserved in PDF text"


# ---------------------------------------------------------------------------
# 2026-04-21 brand-parity: dark PDF brain-icon must not be solid black
# ---------------------------------------------------------------------------
import importlib.util as _importlib_util


def test_leaderboard_contains_tok_s_header():
    """Leaderboard page 3 now has a TOK/S column (new in 2026-04-21)."""
    pages = _extract_pages(generate_pdf(RUN_128, "light"))
    # page index 2 is leaderboard (slide 3)
    assert "TOK/S" in pages[2], pages[2][:500]
    assert "AVG LATENCY" in pages[2], pages[2][:500]


@pytest.mark.skip(
    reason="Brain icons were retired 2026-04-21 (user directive). The "
           "[Reasoning …] suffix in the model name is the authoritative "
           "reasoning marker — this raster probe no longer applies."
)
@pytest.mark.skipif(
    _importlib_util.find_spec("pypdfium2") is None,
    reason="pypdfium2 not installed",
)
def test_dark_pdf_brain_icon_is_not_solid_black():
    """The dark PDF must render brain icons with the muted-foreground grey,
    not the solid black that resulted from WeasyPrint's broken currentColor
    inheritance before the 2026-04-21 fix.

    Uses a bounding-box locator to avoid hardcoded pixel coordinates that
    would break when leaderboard row positions shift with the new columns.
    """
    import io
    import pypdfium2
    from app.core.exports.brand_tokens import get_tokens

    pdf_bytes = generate_pdf(RUN_128, "dark")
    pdf = pypdfium2.PdfDocument(io.BytesIO(pdf_bytes))
    page = pdf[2]  # leaderboard (slide 3, 0-indexed)
    bitmap = page.render(scale=200 / 72.0)
    img = bitmap.to_pil().convert("RGB")
    W, H = img.size

    expected = get_tokens("dark")["muted_foreground"]
    # MODEL column bbox: left quarter of the page, excluding the top header
    # and the bottom footer. Covers every reasoning-model row's icon area.
    l = 0
    r = int(W * 0.30)
    t = int(H * 0.15)
    b = int(H * 0.90)
    crop = img.crop((l, t, r, b))
    pixels = list(crop.getdata())

    def _dist(a, e):
        return max(abs(a[i] - e[i]) for i in range(3))

    matched = sum(1 for px in pixels if _dist(px, expected) <= 24)
    # If the brain icons were rendered black (the pre-fix bug), `matched`
    # would be near-zero: muted-foreground grey (~#A1A1A1) and black do
    # not overlap within any reasonable tolerance. A correctly-fixed dark
    # PDF produces hundreds of stroke pixels for each reasoning-model row
    # at 200 DPI. (We don't count black pixels separately — the dark-
    # theme page background is also near-black, so the count would be
    # dominated by background and give no signal.)
    assert matched >= 30, (
        f"too few muted-foreground-matching pixels inside MODEL bbox — "
        f"matched={matched} expected_hex={expected}. Pre-fix regression: "
        f"brain icons rendered black instead of muted-foreground grey."
    )
