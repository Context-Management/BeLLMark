"""PDF export generator — WeasyPrint-backed HTML→PDF renderer.

This module used to hand-layout a 7-page A4 landscape PDF with fpdf primitives.
That approach produced overlapping text on the cover slide because fpdf has no
layout engine — every element has to be absolutely positioned in millimeters
and bounded by the author. Moving to WeasyPrint means we reuse the HTML export
(which already renders beautifully in Chromium and matches the approved
``docs/export-redesign/mockups/``) and let a CSS engine own the layout.

Design decisions
----------------
* We call :func:`app.core.exports.html_export.generate_html` with the new
  ``slides_only=True`` parameter. That flag drops the archival appendix and
  emits print-oriented ``@page`` CSS sized to the logical 1920×1080 slide
  canvas, so WeasyPrint produces one PDF page per ``<section class="slide">``
  with zero scaling artifacts.
* Page size is 1920×1080 CSS pixels (16:9 slide-deck aspect, matches PPTX
  13.333×7.5 inches at 144 dpi and the source mockup PNGs). Non-standard
  paper but consistent with how Keynote / PowerPoint / Google Slides export
  slide decks to PDF.
* All text — including the Scene 4b methodology paragraph on slide 5 —
  remains real searchable text in the PDF (WeasyPrint preserves the text
  layer). ``pdftotext`` / ``pypdf`` extraction continue to find every
  :data:`app.core.exports.brand_tokens.SCENE_4B_REQUIRED_TERMS`.
* Unicode: WeasyPrint uses the fonts declared in the HTML's ``font-family``
  stack and falls back to system fonts. We no longer need bundled TTFs or
  the lossy ``sanitize_text_for_pdf`` downgrade — emoji, CJK, curly quotes,
  em-dashes all render natively (same as the HTML export). The previously
  bundled ``assets/fonts/DejaVuSans*.ttf`` are removed in this change.
* Signature is unchanged: ``generate_pdf(data: dict, theme: str = "light")
  -> bytes``. Callers (``backend/app/api/results.py``) need no edits.

Graceful degradation: inherited from ``generate_html`` — when ``statistics``,
``bias_report``, or ``calibration_report`` are ``None`` the corresponding
slides render the placeholder text defined by sf-02, and the full methodology
paragraph still appears on slide 5 so the Scene 4b contract holds.
"""
from __future__ import annotations

import re
from io import BytesIO

import pypdf
from weasyprint import HTML

from app.core.exports.html_export import generate_html

# Fixed number of slides in the redesigned deck — enforced at post-process
# time. Rendering each slide individually (rather than letting WeasyPrint
# paginate the full document) guarantees 1:1 slide→page mapping even when a
# single slide's content slightly exceeds the 1080px page (e.g., slide 5's
# stats-rigor matrix + legends). Each per-slide render is trimmed to its
# first page, then the 7 single-page PDFs are concatenated with pypdf.
_EXPECTED_PAGES = 7

# Regex that isolates each `<section class="slide" …>…</section>` block from
# the slides-only HTML. Uses a non-greedy match to avoid spanning siblings.
# Slide sections in the redesigned HTML do not contain nested <section> tags
# inside their `.slide` root, so non-greedy matching is safe.
_SLIDE_RE = re.compile(
    r'<section class="slide".*?</section>',
    re.DOTALL,
)


def generate_pdf(data: dict, theme: str = "light") -> bytes:
    """Render the 7-slide summary deck as a PDF.

    Args:
        data: prepared export payload (see :func:`prepare_export_data`).
        theme: ``"light"`` or ``"dark"``. Invalid values silently fall back
            to ``"light"`` — matching the tolerant behavior of
            ``generate_html`` / ``generate_pptx``.

    Returns:
        Raw PDF bytes (starts with ``%PDF``). Exactly 7 pages, 16:9 each,
        1920×1080 CSS pixels.
    """
    if theme not in ("light", "dark"):
        theme = "light"

    # Reuse the HTML export's slide-rendering pipeline in slides-only mode.
    # `slides_only=True` drops the archival appendix and emits print-oriented
    # `@page` CSS sized for 1920×1080 slide-deck pages.
    full_html = generate_html(data, theme, slides_only=True)

    # Split the full slides-only HTML into 7 independent slide sections and
    # render each separately. We cannot rely on whole-document pagination:
    # when a slide's content slightly overflows 1080px (e.g., slide 5's
    # stats-rigor matrix + 3 legends) WeasyPrint paginates INSIDE that slide,
    # shifting every subsequent slide onto the wrong page. Per-slide
    # rendering gives us a deterministic 1:1 slide→page mapping.
    head_match = re.search(r"<head>(.*?)</head>", full_html, re.DOTALL)
    head_inner = head_match.group(1) if head_match else ""

    slide_blocks = _SLIDE_RE.findall(full_html)
    if len(slide_blocks) != _EXPECTED_PAGES:
        raise RuntimeError(
            f"generate_html(slides_only=True) produced {len(slide_blocks)} "
            f"slide sections; expected {_EXPECTED_PAGES}. This indicates a "
            "structural change in html_export.py that this module was not "
            "updated for."
        )

    writer = pypdf.PdfWriter()
    for slide_html in slide_blocks:
        single = (
            "<!DOCTYPE html><html lang=\"en\"><head>"
            + head_inner
            + "</head><body>"
            + slide_html
            + "</body></html>"
        )
        page_bytes = HTML(string=single).write_pdf()
        if not page_bytes:
            raise RuntimeError("WeasyPrint returned no PDF bytes for a slide.")
        # Each slide renders to 1+ pages (may overflow). Take page 0 only so
        # the final document has exactly one page per slide.
        reader = pypdf.PdfReader(BytesIO(page_bytes))
        writer.add_page(reader.pages[0])

    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()
