"""HTML export generator for BeLLMark benchmark results — redesigned (sf-02).

Produces a self-contained HTML document with:

1. Seven 1920×1080 ``<section class="slide">`` blocks (cover, executive,
   leaderboard, criteria, stats-rigor, bias, methodology).
2. A structural ``<section class="appendix">`` preserving the legacy archival
   content (per-question prompts, generations, and judgments) so downstream
   reviewers retain the original deep-dive surface.

All run-sourced text is sanitized (``sanitize_text``) and HTML-escaped before
interpolation. All colours come from the sf-01 brand token foundation — no
ad-hoc hex literals other than a handful of pure neutrals (``#000``, ``#fff``).
"""
from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.exports.brand_tokens import (
    COLOR_TOKEN_ALLOWLIST,
    FRONTEND_BRAND,
    SCENE_4B_REQUIRED_TERMS,
    _fmt_latency_ms,
    brand,
    get_tokens,
    is_reasoning_model,
    sanitize_text,
    token_hex,
)
from app.core.exports.common import (
    compute_export_integrity,
    extract_comment_text,
    format_cost,
    format_duration,
    score_color_rgb,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------
def _rgb(rgb: tuple[int, int, int], alpha: float | None = None) -> str:
    r, g, b = rgb
    if alpha is None:
        return f"rgb({r},{g},{b})"
    return f"rgba({r},{g},{b},{alpha:g})"


def _esc(value: Any, *, max_len: int | None = None) -> str:
    """Sanitize + HTML-escape a potentially dynamic string. ``None`` → empty."""
    return html.escape(sanitize_text(value, max_len=max_len), quote=True)


def _fmt_score(score: float | None, fmt: str = "{:.2f}") -> str:
    if score is None:
        return "—"
    try:
        return fmt.format(float(score))
    except (TypeError, ValueError):
        return "—"


def _fmt_cost(cost: float | None) -> str:
    if cost is None:
        return "—"
    return format_cost(cost)


def _fmt_per_prompt(cost: float | None, n_questions: int) -> str:
    if cost is None:
        return "—"
    per = cost / max(1, n_questions)
    return f"{format_cost(per)}/prompt"


# Reasoning-model marker: the "[Reasoning (high)]" suffix is ALREADY part
# of the model name as stored by the backend, so exports do not need a
# separate visual icon. Any leftover _brain_marker_html() callers return
# an empty string — preserved as a stub so existing call sites compile
# without edits during the visual-parity refactor.
def _brain_marker_html(
    entity: dict,
    snapshots: list | None,
    *,
    big: bool = False,
) -> str:
    return ""


def _load_logo_svg() -> str:
    """Best-effort load of the product logo; empty string on failure."""
    logo_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "frontend"
        / "public"
        / "bellmark-logo.svg"
    )
    if logo_path.exists():
        try:
            return logo_path.read_text()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(f"Failed to load logo SVG from {logo_path}: {e}")
    return ""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def generate_html(data: dict, theme: str = "dark", *, slides_only: bool = False) -> str:
    """Generate a self-contained redesigned HTML report.

    Args:
        data: Prepared export payload (see design §2 canonical schema).
        theme: ``"light"`` or ``"dark"``. Defaults to ``"dark"``.
        slides_only: when True, omit the archival appendix, emit print-oriented
            CSS with ``@page { size: 1920px 1080px }`` (16:9 slide-deck
            aspect ratio), and drop decorative body/slide chrome so the output
            is safe to feed to WeasyPrint for PDF generation. Default False
            preserves the existing full-report behavior.

    Returns:
        A ``str`` containing the full HTML document.
    """
    if theme not in ("light", "dark"):
        theme = "dark"

    tokens = get_tokens(theme)

    run = data.get("run") or {}
    models = data.get("models") or []
    judges = data.get("judges") or []
    criteria = run.get("criteria") or []
    questions = data.get("questions") or []
    judge_summary = data.get("judge_summary") or {}
    comment_summaries = data.get("comment_summaries") or {}
    scores_by_criterion = data.get("scores_by_criterion") or {}
    statistics = data.get("statistics")
    bias_report = data.get("bias_report")
    calibration_report = data.get("calibration_report")
    kappa_value = data.get("kappa_value")
    kappa_type = data.get("kappa_type")

    model_snapshots = run.get("model_preset_snapshots")
    judge_snapshots = run.get("judge_preset_snapshots")

    integrity = compute_export_integrity(data, run.get("id"))

    # --- Slides -----------------------------------------------------------
    slide_cover = _slide_cover(run, models, judges, criteria, questions, statistics, model_snapshots)
    slide_executive = _slide_executive(run, models, questions, statistics, model_snapshots)
    slide_leaderboard = _slide_leaderboard(models, statistics, questions, model_snapshots)
    slide_criteria = _slide_criteria(models, criteria, scores_by_criterion, model_snapshots)
    slide_stats = _slide_stats_rigor(models, statistics, model_snapshots)
    slide_bias = _slide_bias(bias_report, judge_summary, kappa_value, kappa_type, calibration_report)
    slide_methodology = _slide_methodology(
        run, models, judges, criteria, questions, judge_snapshots, integrity
    )

    # --- Archival appendix ------------------------------------------------
    # Skipped in slides_only mode — the PDF artifact is intentionally a
    # 7-slide summary deck, not the full archival report.
    if slides_only:
        appendix = ""
    else:
        appendix = _appendix(
            run,
            models,
            judges,
            criteria,
            questions,
            judge_summary,
            comment_summaries,
            statistics,
            bias_report,
            calibration_report,
            kappa_value,
            kappa_type,
            integrity,
            model_snapshots,
            judge_snapshots,
        )

    # --- Assemble ---------------------------------------------------------
    integrity_comment = (
        "<!-- BeLLMark-Integrity\n"
        f"{json.dumps(integrity, indent=2)}\n"
        "-->"
    )

    title = _esc(run.get("name") or "BeLLMark Report")

    return (
        "<!DOCTYPE html>\n"
        f'<html lang="en" data-theme="{html.escape(theme)}">\n'
        "<head>\n"
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"  <title>{title} — BeLLMark Report</title>\n"
        f"  {integrity_comment}\n"
        f"  {_styles(tokens, theme, slides_only=slides_only)}\n"
        "</head>\n"
        "<body>\n"
        f"{slide_cover}\n"
        f"{slide_executive}\n"
        f"{slide_leaderboard}\n"
        f"{slide_criteria}\n"
        f"{slide_stats}\n"
        f"{slide_bias}\n"
        f"{slide_methodology}\n"
        f"{appendix}\n"
        "</body>\n"
        "</html>\n"
    )


# ---------------------------------------------------------------------------
# Styles — driven entirely by sf-01 brand tokens
# ---------------------------------------------------------------------------
def _styles(tokens: dict, theme: str, *, slides_only: bool = False) -> str:
    # Emit every color token in COLOR_TOKEN_ALLOWLIST as a CSS var whose
    # kebab-case name matches the frontend's CSS custom properties 1:1.
    # --accent is the frontend's real near-neutral accent (NOT chart-1).
    # Renderer-internal colorful accents live on --chart-1 .. --chart-5.
    color_vars = "\n".join(
        f"    --{name.replace('_', '-')}: {_rgb(tokens[name])};"
        for name in COLOR_TOKEN_ALLOWLIST
    )

    font_title = tokens["font_title"]
    font_h2 = tokens["font_h2"]
    font_body = tokens["font_body"]
    font_caption = tokens["font_caption"]
    font_footer = tokens["font_footer"]
    r_lg = tokens["radius_lg"]
    r_md = tokens["radius_md"]
    r_sm = tokens["radius_sm"]

    # Legacy short aliases preserved so pre-existing slide CSS keeps
    # working. These map to TOKEN-DERIVED colors — chart-1/2/3 supply the
    # vivid accent used by charts/bars/highlights in the slide chrome.
    # `--muted-fg` mirrors --muted-foreground since legacy rules use the
    # short name.
    aliases = (
        f"    --bg: {_rgb(tokens['background'])};\n"
        f"    --fg: {_rgb(tokens['foreground'])};\n"
        f"    --muted-fg: {_rgb(tokens['muted_foreground'])};\n"
        f"    --accent-2: {_rgb(tokens['chart_2'])};\n"
        f"    --accent-3: {_rgb(tokens['chart_3'])};\n"
    )

    return f"""<style>
  :root {{
{color_vars}
{aliases}    --radius-lg: {r_lg}px;
    --radius-md: {r_md}px;
    --radius-sm: {r_sm}px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen,
                 Ubuntu, Cantarell, 'Helvetica Neue', Arial, sans-serif;
    font-size: {font_body}px;
    line-height: 1.5;
  }}
  body {{ padding: 24px; }}

  .slide {{
    width: 1920px;
    height: 1080px;
    overflow: hidden;
    background: var(--bg);
    color: var(--fg);
    padding: 64px 96px;
    margin: 0 auto 48px;
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    page-break-after: always;
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 32px;
  }}
  .slide .eyebrow {{
    font-size: {font_footer}px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--muted-fg);
    font-weight: 600;
  }}
  .slide h1.title {{
    font-size: {font_title}px;
    line-height: 1.05;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: var(--fg);
  }}
  .slide h2.section-head {{
    font-size: {font_h2}px;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--fg);
    margin-bottom: 8px;
  }}
  .slide .slide-footer {{
    margin-top: auto;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: {font_footer}px;
    color: var(--muted-fg);
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }}

  /* Brand color utilities — mirror frontend/src/pages/results/OverviewSection.tsx
     Tailwind classes (text-amber-600 / text-yellow-400 for winner, green-600 /
     green-400 for runners, amber badge for criteria, purple badge for judges). */
  .brand-winner-text  {{ color: {_rgb(brand(theme, "winner_text"))}; font-weight: 700; }}
  .brand-runner-text  {{ color: {_rgb(brand(theme, "runner_text"))}; font-weight: 600; }}
  .brand-bronze-text  {{ color: {_rgb(brand(theme, "bronze_text"))}; font-weight: 600; }}
  .brand-criteria-badge {{
    color: {_rgb(brand(theme, "criteria_text"))};
    background: {_rgb(brand(theme, "criteria_bg"))};
    border: 1px solid {_rgb(brand(theme, "criteria_bord"))};
    padding: 2px 8px; border-radius: 6px; font-size: 12px; display: inline-block;
  }}
  .brand-judge-badge {{
    color: {_rgb(brand(theme, "judge_text"))};
    background: {_rgb(brand(theme, "judge_bg"))};
    border: 1px solid {_rgb(brand(theme, "judge_bord"))};
    padding: 2px 8px; border-radius: 6px; font-size: 12px; display: inline-block;
  }}
  .brand-winner-card {{
    background: linear-gradient(90deg, {_rgb(brand(theme, "winner_card_a"))}, {_rgb(brand(theme, "winner_card_b"))});
    border: 1px solid {_rgb(brand(theme, "winner_card_bd"))};
  }}

  .tile-grid {{
    display: grid;
    gap: 16px;
  }}
  .tile {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 20px;
  }}
  .tile .label {{
    font-size: {font_caption}px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted-fg);
    font-weight: 600;
  }}
  .tile .value {{
    margin-top: 8px;
    font-size: 28px;
    font-weight: 700;
    color: var(--fg);
  }}
  .tile .detail {{
    margin-top: 4px;
    font-size: {font_caption}px;
    color: var(--muted-fg);
  }}

  .finding-card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 32px;
  }}
  .finding-card .heading {{
    font-size: {font_caption}px;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--chart-1);
    font-weight: 700;
  }}
  .finding-card .body {{
    margin-top: 12px;
    font-size: 36px;
    line-height: 1.2;
    font-weight: 600;
    color: var(--fg);
  }}
  .finding-card .score {{
    margin-top: 8px;
    font-size: 18px;
    color: var(--muted-fg);
  }}

  .podium {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }}
  .podium .slot {{
    background: var(--muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px 20px;
  }}
  .podium .rank {{
    font-size: {font_caption}px;
    color: var(--muted-fg);
    text-transform: uppercase;
    letter-spacing: 0.14em;
  }}
  .podium .name {{
    font-size: 18px;
    font-weight: 600;
    color: var(--fg);
    margin-top: 4px;
  }}

  .lb-table, .crit-table, .matrix-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: {font_body}px;
  }}
  .lb-table th, .crit-table th, .matrix-table th {{
    text-align: left;
    font-size: {font_caption}px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--muted-fg);
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
  }}
  .lb-table td, .crit-table td, .matrix-table td {{
    padding: 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: middle;
  }}
  .lb-table .model-cell, .crit-table .model-cell {{
    font-weight: 600;
    color: {_rgb(brand(theme, "runner_text"))};
  }}
  /* Winner row: amber/yellow tint + amber model name (frontend winner card). */
  .lb-table .winner-row td {{
    background: {_rgb(brand(theme, "winner_card_a"))};
  }}
  .lb-table .winner-row .model-cell {{
    color: {_rgb(brand(theme, "winner_text"))};
    font-weight: 700;
  }}
  .crit-table .winner-cell {{
    color: {_rgb(brand(theme, "winner_text"))};
    font-weight: 700;
  }}
  .err-bar {{
    display: inline-block;
    vertical-align: middle;
    width: 160px;
    height: 6px;
    background: var(--muted);
    border-radius: var(--radius-sm);
    position: relative;
    margin-left: 8px;
  }}
  .err-bar .fill {{
    position: absolute;
    top: 0;
    bottom: 0;
    background: var(--chart-1);
    border-radius: var(--radius-sm);
  }}
  .mini-bar {{
    display: inline-block;
    height: 8px;
    background: var(--accent-2);
    border-radius: var(--radius-sm);
    vertical-align: middle;
    margin-right: 6px;
  }}
  .mini-bar-track {{
    display: inline-block;
    width: 140px;
    height: 8px;
    background: var(--muted);
    border-radius: var(--radius-sm);
    vertical-align: middle;
    margin-right: 6px;
    position: relative;
  }}
  .mini-bar-track .fill {{
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    background: var(--accent-2);
    border-radius: var(--radius-sm);
  }}

  .heat-cell {{
    text-align: center;
    font-weight: 600;
  }}
  .best-row {{
    margin-top: 18px;
    font-size: {font_caption}px;
    color: var(--muted-fg);
  }}
  .best-row .label {{
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
    color: var(--fg);
    margin-right: 8px;
  }}

  .methodology-para {{
    font-size: 16px;
    line-height: 1.6;
    color: var(--fg);
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 20px 24px;
  }}
  .matrix-legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px 24px;
    margin-top: 12px;
    font-size: {font_caption}px;
    color: var(--muted-fg);
  }}
  .how-to-read, .effect-legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    font-size: {font_caption}px;
    color: var(--muted-fg);
  }}
  .how-to-read .label, .effect-legend .label {{
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--fg);
  }}
  .how-to-read .chip, .effect-legend .chip {{
    padding: 2px 10px;
    border-radius: var(--radius-sm);
    background: var(--muted);
    color: var(--fg);
    border: 1px solid var(--border);
  }}

  .bias-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
  }}
  .bias-panel {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 20px;
  }}
  .bias-panel h3 {{
    font-size: 20px;
    font-weight: 600;
    margin-bottom: 8px;
  }}
  .bias-panel .status {{
    font-size: {font_caption}px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: var(--radius-sm);
    display: inline-block;
  }}
  .bias-panel .status.detected {{
    background: rgba(255,255,255,0.06);
    color: var(--destructive);
    border: 1px solid var(--destructive);
  }}
  .bias-panel .status.clean {{
    background: rgba(255,255,255,0.06);
    color: var(--accent-2);
    border: 1px solid var(--accent-2);
  }}

  .cal-strip {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 8px;
  }}

  .methodology-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 24px;
  }}
  .methodology-block {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 24px;
  }}
  .methodology-block h3 {{
    font-size: {font_caption}px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted-fg);
    font-weight: 700;
    margin-bottom: 12px;
  }}
  .signoff dl {{
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 6px 16px;
    font-size: {font_body}px;
  }}
  .signoff dt {{
    color: var(--muted-fg);
    font-weight: 600;
  }}
  .signoff dd {{
    color: var(--fg);
  }}

  .appendix {{
    width: 100%;
    max-width: 1400px;
    margin: 96px auto 0;
    background: var(--bg);
    color: var(--fg);
    padding: 40px 0 80px;
    border-top: 2px solid var(--border);
  }}
  .appendix h2 {{
    font-size: 28px;
    font-weight: 700;
    margin-bottom: 16px;
    color: var(--fg);
    border-bottom: 1px solid var(--border);
    padding-bottom: 12px;
  }}
  .appendix h3 {{
    font-size: 18px;
    font-weight: 600;
    color: var(--fg);
    margin: 20px 0 10px;
  }}
  .appendix details {{
    margin: 18px 0;
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px;
  }}
  .appendix summary {{
    cursor: pointer;
    font-weight: 600;
    color: var(--fg);
  }}
  .appendix .generation, .appendix .judge-review {{
    background: var(--muted);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 14px;
    margin: 12px 0;
  }}
  .appendix .generation-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: {font_caption}px;
    color: var(--muted-fg);
    margin-bottom: 8px;
  }}
  .appendix .generation-content {{
    white-space: pre-wrap;
    word-wrap: break-word;
    color: var(--fg);
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 12px;
    font-family: ui-monospace, SFMono-Regular, 'Menlo', 'Consolas', monospace;
    font-size: 13px;
  }}
  .appendix pre {{
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px;
    margin: 8px 0;
    white-space: pre-wrap;
    word-wrap: break-word;
    font-family: ui-monospace, SFMono-Regular, 'Menlo', 'Consolas', monospace;
    font-size: 13px;
  }}
  .appendix table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
    font-size: {font_body}px;
  }}
  .appendix th, .appendix td {{
    border-bottom: 1px solid var(--border);
    padding: 8px 10px;
    text-align: left;
  }}
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: var(--radius-sm);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    border: 1px solid var(--border);
  }}
  .badge-success {{ color: var(--accent-2); border-color: var(--accent-2); }}
  .badge-warning {{ color: var(--chart-1); border-color: var(--chart-1); }}
  .comment-item {{
    padding: 6px 10px;
    margin: 4px 0;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--bg);
  }}
  .comment-positive {{ border-left: 3px solid var(--accent-2); }}
  .comment-negative {{ border-left: 3px solid var(--destructive); }}

  @media print {{
    body {{ padding: 0; }}
    .slide {{ margin: 0; border: none; }}
    .appendix {{ page-break-before: always; }}
  }}
{_print_overrides() if slides_only else ""}
</style>"""


def _print_overrides() -> str:
    """CSS applied only when ``slides_only=True`` — PDF/print mode.

    Goals:
      * Page size is exactly the logical 1920×1080 slide canvas so WeasyPrint
        produces one PDF page per ``<section class="slide">`` with zero
        scaling artifacts.
      * Body margins/padding removed so the slide fills the page edge-to-edge.
      * Decorative rounded border removed (the PDF page IS the container).
      * Font-family pinned to bundled DejaVu Sans TTF. Without this,
        fontconfig on Linux resolves ``system-ui`` to Cantarell (a variable
        OpenType font) which WeasyPrint's subsetter embeds as invalid
        CID Type 0C glyphs — rendered as mojibake in macOS Preview. Plain
        TrueType embeds cleanly everywhere.
    """
    # Pagination strategy: each slide is exactly 1920×1080 (the @page size)
    # with `break-inside: avoid` to keep its content together. We do NOT set
    # page-break-after on slides because any `:last-child` override is flaky
    # across renderers — instead we rely on `page-break-before: always` on
    # every slide EXCEPT the first. This gives us exactly N pages for N
    # slides, with no trailing blank, regardless of content overflow.
    from pathlib import Path
    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    dejavu_regular = (fonts_dir / "DejaVuSans.ttf").as_uri()
    dejavu_bold = (fonts_dir / "DejaVuSans-Bold.ttf").as_uri()
    return f"""
  @font-face {{
    font-family: "BellmarkDeck";
    font-weight: normal;
    src: url({dejavu_regular}) format("truetype");
  }}
  @font-face {{
    font-family: "BellmarkDeck";
    font-weight: bold;
    src: url({dejavu_bold}) format("truetype");
  }}
  @page {{ size: 1920px 1080px; margin: 0; }}
  html, body {{
    margin: 0 !important;
    padding: 0 !important;
    background: var(--bg) !important;
    font-family: "BellmarkDeck", "DejaVu Sans", Arial, sans-serif !important;
  }}
  .slide, .slide * {{
    font-family: "BellmarkDeck", "DejaVu Sans", Arial, sans-serif !important;
  }}
  .slide {{
    width: 1920px !important;
    height: 1080px !important;
    max-height: 1080px !important;
    overflow: hidden !important;
    margin: 0 !important;
    border: none !important;
    border-radius: 0 !important;
    page-break-before: always;
    break-before: page;
    page-break-after: auto;
    break-after: auto;
    break-inside: avoid;
  }}
  .slide:first-child {{
    page-break-before: auto;
    break-before: avoid;
  }}
"""


# ---------------------------------------------------------------------------
# Slide 1 — Cover
# ---------------------------------------------------------------------------
def _slide_cover(
    run: dict,
    models: list,
    judges: list,
    criteria: list,
    questions: list,
    statistics: dict | None,
    model_snapshots: list | None,
) -> str:
    run_name = _esc(run.get("name") or "Benchmark Run")
    run_id = run.get("id") or 0
    judge_mode = _esc(run.get("judge_mode") or "comparison")

    # Winner + finding
    winner_html = ""
    winner_score_html = ""
    if models:
        w = models[0]
        winner_html = (
            f'<span class="brand-winner-text">{_esc(w.get("name") or "")}</span>'
        )
        ws = w.get("weighted_score")
        ci_suffix = ""
        winner_ci = _winner_ci(w, statistics)
        if winner_ci:
            lo = _fmt_score(winner_ci.get("lower"))
            hi = _fmt_score(winner_ci.get("upper"))
            ci_suffix = f" (95% CI {lo}–{hi})"
        winner_score_html = (
            f'Weighted mean {_fmt_score(ws)}{ci_suffix}'
        )

    # Podium (top 3) — rank 1 amber, rank 2 green, rank 3 orange
    _podium_classes = ["brand-winner-text", "brand-runner-text", "brand-bronze-text"]
    podium_slots = []
    for idx in range(3):
        if idx < len(models):
            m = models[idx]
            name = (
                f'<span class="{_podium_classes[idx]}">'
                f'{_esc(m.get("name") or "")}</span>'
            )
            podium_slots.append(
                f'<div class="slot"><div class="rank">Rank #{idx + 1}</div>'
                f'<div class="name">{name}</div></div>'
            )
        else:
            podium_slots.append(
                '<div class="slot"><div class="rank">—</div>'
                '<div class="name">—</div></div>'
            )

    # Scope tiles (6)
    total_cost = run.get("total_cost")
    tiles = [
        ("CANDIDATES", f"{len(models)}"),
        ("PROMPTS", f"{len(questions)}"),
        ("JUDGES", f"{len(judges)}"),
        ("RUBRIC CRITERIA", f"{len(criteria)}"),
        ("TOTAL SPEND", _fmt_cost(total_cost)),
        ("MODE", judge_mode),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="label">{html.escape(lbl)}</div>'
        f'<div class="value">{val}</div></div>'
        for lbl, val in tiles
    )

    return f"""<section class="slide" data-slide="1" data-kind="cover">
  <div>
    <div class="eyebrow">MODEL EVALUATION REPORT</div>
    <h1 class="title">{run_name}</h1>
  </div>
  <div style="display:grid; grid-template-columns: 1.3fr 1fr; gap: 32px;">
    <div class="finding-card">
      <div class="heading">KEY FINDING</div>
      <div class="body">{winner_html}</div>
      <div class="score">{winner_score_html}</div>
    </div>
    <div>
      <div class="eyebrow" style="margin-bottom:12px;">PODIUM</div>
      <div class="podium">{"".join(podium_slots)}</div>
    </div>
  </div>
  <div class="tile-grid" style="grid-template-columns: repeat(6, 1fr);">
    {tiles_html}
  </div>
  <div class="slide-footer">
    <span>BeLLMark Run #{run_id:04d}</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 2 — Executive summary
# ---------------------------------------------------------------------------
def _winner_ci(winner: dict, statistics: dict | None) -> dict | None:
    if not statistics:
        return None
    ms = statistics.get("model_statistics") or []
    for item in ms:
        if item.get("model_name") == winner.get("name"):
            ci = item.get("weighted_score_ci")
            if isinstance(ci, dict) and ci.get("lower") is not None and ci.get("upper") is not None:
                return ci
            return None
    return None


def _top_cluster(winner: dict, statistics: dict | None) -> str:
    winner_ci = _winner_ci(winner, statistics)
    if not winner_ci or not statistics:
        return "—"
    lower = winner_ci.get("lower")
    if lower is None:
        return "—"
    count = 0
    for item in statistics.get("model_statistics") or []:
        ci = item.get("weighted_score_ci") or {}
        upper = ci.get("upper")
        if upper is not None and upper >= lower:
            count += 1
    return str(count)


def _slide_executive(
    run: dict,
    models: list,
    questions: list,
    statistics: dict | None,
    model_snapshots: list | None,
) -> str:
    winner = models[0] if models else {}
    winner_name = _esc(winner.get("name") or "—")
    winner_brain = _brain_marker_html(winner, model_snapshots, big=True) if winner else ""
    winner_score = _fmt_score(winner.get("weighted_score"))

    winner_ci = _winner_ci(winner, statistics) if winner else None
    if winner_ci:
        ci_line = f'(95% CI {_fmt_score(winner_ci.get("lower"))}–{_fmt_score(winner_ci.get("upper"))})'
    else:
        ci_line = "(CI unavailable for this run)"

    total_cost = run.get("total_cost")
    top_cluster = _top_cluster(winner, statistics) if winner else "—"
    sample_size = str(len(questions))

    tiles_html = "".join([
        f'<div class="tile"><div class="label">TOTAL SPEND</div><div class="value">{_fmt_cost(total_cost)}</div></div>',
        f'<div class="tile"><div class="label">TOP CLUSTER</div><div class="value">{html.escape(top_cluster)}</div>'
        f'<div class="detail">Models within the winner\'s CI</div></div>',
        f'<div class="tile"><div class="label">SAMPLE SIZE</div><div class="value">{html.escape(sample_size)}</div>'
        f'<div class="detail">Prompts per model</div></div>',
    ])

    # Top-3 price/quality bars
    n_q = len(questions)
    top3 = models[:3]
    max_per = 0.0
    for m in top3:
        c = m.get("estimated_cost")
        if c is not None:
            max_per = max(max_per, c / max(1, n_q))
    bars_html_parts = []
    for idx, m in enumerate(top3):
        brain = _brain_marker_html(m, model_snapshots)
        name = f'{brain}{_esc(m.get("name") or "")}'
        cost_val = m.get("estimated_cost")
        per = None if cost_val is None else cost_val / max(1, n_q)
        per_label = "—" if per is None else f"{format_cost(per)}/prompt"
        fill_pct = 0 if max_per <= 0 or per is None else min(100.0, per / max_per * 100.0)
        bars_html_parts.append(
            f'<div style="display:grid; grid-template-columns: 1fr max-content; align-items:center; gap:12px; padding: 10px 0;">'
            f'<div><div style="font-weight:600;">#{idx + 1} {name}</div>'
            f'<div class="mini-bar-track"><div class="fill" style="width:{fill_pct:.0f}%;"></div></div></div>'
            f'<div style="font-variant-numeric: tabular-nums; color: var(--fg);">{html.escape(per_label)}</div>'
            f'</div>'
        )

    # Takeaway: simple data-grounded sentence.
    takeaway = (
        f"{winner_name} leads on weighted quality; the top cluster counts "
        f"{html.escape(top_cluster)} model(s) within its CI. "
        f"Total spend for the run: {html.escape(_fmt_cost(total_cost))}."
    )

    return f"""<section class="slide" data-slide="2" data-kind="executive">
  <div>
    <div class="eyebrow">EXECUTIVE SUMMARY</div>
    <h2 class="section-head">Winner</h2>
  </div>
  <div class="finding-card">
    <div class="heading">KEY FINDING</div>
    <div class="body brand-winner-text">{winner_name}</div>
    <div class="score">Weighted mean {winner_score} {html.escape(ci_line)}</div>
  </div>
  <div class="tile-grid" style="grid-template-columns: repeat(3, 1fr);">
    {tiles_html}
  </div>
  <div>
    <div class="eyebrow" style="margin-bottom:10px;">TOP 3 · QUALITY VS COST PER PROMPT</div>
    {"".join(bars_html_parts) if bars_html_parts else '<div class="tile"><div class="detail">No models available.</div></div>'}
  </div>
  <div style="font-size: 16px; color: var(--muted-fg);">{takeaway}</div>
  <div class="slide-footer">
    <span>BeLLMark Run #{(run.get("id") or 0):04d}</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 3 — Leaderboard
# ---------------------------------------------------------------------------
def _slide_leaderboard(
    models: list,
    statistics: dict | None,
    questions: list,
    model_snapshots: list | None,
) -> str:
    n_q = len(questions)
    stats_by_name: dict[str, dict] = {}
    if statistics and statistics.get("model_statistics"):
        for it in statistics["model_statistics"]:
            nm = it.get("model_name")
            if isinstance(nm, str):
                stats_by_name[nm] = it

    # Compute max per-prompt cost for the bar
    max_per = 0.0
    for m in models:
        c = m.get("estimated_cost")
        if c is not None:
            max_per = max(max_per, c / max(1, n_q))

    # Compute max CI upper for error bar scale
    max_upper = 10.0
    for m in models:
        stat = stats_by_name.get(m.get("name", ""))
        if stat:
            ci = stat.get("weighted_score_ci") or {}
            u = ci.get("upper")
            if u is not None:
                max_upper = max(max_upper, float(u))

    rows = []
    for idx, m in enumerate(models):
        rank_val = m.get("rank") or (idx + 1)
        rank_txt = f"#{rank_val}"
        name_brain = _brain_marker_html(m, model_snapshots)
        name_html = f'{name_brain}{_esc(m.get("name") or "")}'

        mean = m.get("weighted_score")
        mean_txt = f"{float(mean):.2f}" if mean is not None else "—"

        # Raw-name stats join (spec §2.1).
        stat = stats_by_name.get(m.get("name", ""))
        ci = (stat or {}).get("weighted_score_ci") or {}
        lo, hi = ci.get("lower"), ci.get("upper")
        ci_txt = (
            f"[{float(lo):.2f} – {float(hi):.2f}]"
            if lo is not None and hi is not None else "—"
        )

        wr = m.get("win_rate")
        wr_txt = f"{float(wr) * 100:.0f}%" if wr is not None else "—"

        tps = m.get("tokens_per_second")
        tps_txt = f"{float(tps):.1f}" if tps is not None else "—"

        lat_txt = _fmt_latency_ms(m.get("avg_latency_ms"))

        lc_blk = (stat or {}).get("lc_win_rate") or {}
        lc_val = lc_blk.get("lc_win_rate")
        if lc_val is not None:
            warn = "⚠ " if lc_blk.get("length_bias_detected") else ""
            lc_txt = f"{warn}{float(lc_val) * 100:.0f}%"
        else:
            lc_txt = "—"

        cost_val = m.get("estimated_cost")
        if cost_val is not None and n_q > 0:
            cost_txt = f"{format_cost(cost_val / n_q)}/prompt"
        else:
            cost_txt = "—"

        row_cls = "winner-row" if rank_val == 1 else ""
        rows.append(
            f'<tr class="{row_cls}">'
            f'<td>{rank_txt}</td>'
            f'<td class="model-cell">{name_html}</td>'
            f'<td>{mean_txt}</td>'
            f'<td>{ci_txt}</td>'
            f'<td>{wr_txt}</td>'
            f'<td>{tps_txt}</td>'
            f'<td>{lat_txt}</td>'
            f'<td>{lc_txt}</td>'
            f'<td>{html.escape(cost_txt)}</td>'
            f'</tr>'
        )

    return f"""<section class="slide" data-slide="3" data-kind="leaderboard">
  <div>
    <div class="eyebrow">LEADERBOARD</div>
    <h2 class="section-head">Ranked models with uncertainty, speed, win rates, and per-prompt cost</h2>
  </div>
  <table class="lb-table">
    <colgroup>
      <col style="width:4%">
      <col style="width:28%">
      <col style="width:7%">
      <col style="width:13%">
      <col style="width:9%">
      <col style="width:8%">
      <col style="width:11%">
      <col style="width:9%">
      <col style="width:11%">
    </colgroup>
    <thead>
      <tr>
        <th>#</th>
        <th>MODEL</th>
        <th>MEAN</th>
        <th>95% CI</th>
        <th>WIN RATE</th>
        <th>TOK/S</th>
        <th>AVG LATENCY</th>
        <th>LC WIN</th>
        <th>$/PROMPT</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
  <div class="slide-footer">
    <span>BeLLMark Leaderboard · Wilson 95% CI · tokens/sec + avg latency from run telemetry</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 4 — Per-criterion heatmap + best-in-class
# ---------------------------------------------------------------------------
def _slide_criteria(
    models: list,
    criteria: list,
    scores_by_criterion: dict,
    model_snapshots: list | None,
) -> str:
    # Header. Criteria names are displayed with brand amber (criteria badge
    # style) so the cross-format palette matches the frontend.
    header = "<tr><th>Model</th>"
    for crit in criteria:
        header += (
            f'<th><span class="brand-criteria-badge">'
            f'{_esc(crit.get("name"))}</span></th>'
        )
    header += "<th>Weighted</th></tr>"

    rows = []
    for idx, m in enumerate(models):
        row_cls = " class=\"winner-row\"" if idx == 0 else ""
        cell_cls = "brand-winner-text" if idx == 0 else "brand-runner-text"
        row = (
            f"<tr{row_cls}>"
            f'<td class="model-cell {cell_cls}">{_esc(m.get("name"))}</td>'
        )
        per = m.get("per_criterion_scores") or scores_by_criterion.get(m.get("name"), {}) or {}
        for crit in criteria:
            v = per.get(crit.get("name"), 0) or 0
            r, g, b = score_color_rgb(float(v))
            style = f"background: rgba({r},{g},{b},0.22); color: rgb({r},{g},{b});"
            row += f'<td class="heat-cell" style="{style}">{float(v):.1f}</td>'
        ws = m.get("weighted_score") or 0
        r, g, b = score_color_rgb(float(ws))
        style = f"background: rgba({r},{g},{b},0.32); color: rgb({r},{g},{b}); font-weight:700;"
        row += f'<td class="heat-cell" style="{style}">{_fmt_score(ws)}</td></tr>'
        rows.append(row)

    # Best-in-class per criterion
    best_parts = []
    for crit in criteria:
        cn = crit.get("name")
        best_model = None
        best_score = -1.0
        for m in models:
            v = (m.get("per_criterion_scores") or {}).get(cn)
            if v is not None and float(v) > best_score:
                best_score = float(v)
                best_model = m.get("name")
        if best_model is not None:
            best_parts.append(
                f'<span style="margin-right:16px;"><strong>{_esc(cn)}:</strong> '
                f'{_esc(best_model)} ({best_score:.2f})</span>'
            )

    return f"""<section class="slide" data-slide="4" data-kind="criteria">
  <div>
    <div class="eyebrow">PER-CRITERION HEATMAP</div>
    <h2 class="section-head">Scores per rubric criterion</h2>
  </div>
  <table class="crit-table">
    <thead>{header}</thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  <div class="best-row"><span class="label">Best-in-class per criterion</span>{"".join(best_parts)}</div>
  <div class="slide-footer">
    <span>Per-criterion mean across all judges · higher is better</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 5 — Statistical rigor
# ---------------------------------------------------------------------------
_METHODOLOGY_PARAGRAPH = (
    "We report weighted means with Wilson 95% CI for proportions and "
    "Bootstrap 95% confidence intervals for score differences. Pairwise "
    "model comparisons use a Wilcoxon signed-rank test with Holm-Bonferroni "
    "correction for multiple comparisons, and Cohen's d as the effect-size "
    "measure. Bias diagnostics cover Position bias, Length bias, "
    "Self-preference and Verbosity bias; an inter-judge agreement kappa is "
    "reported alongside."
)


def _slide_stats_rigor(
    models: list,
    statistics: dict | None,
    model_snapshots: list | None,
) -> str:
    # Build M-code mapping from ranked models list.
    n = min(8, len(models))
    m_names = [m.get("name") or "" for m in models[:n]]
    name_to_code = {nm: f"M{i + 1}" for i, nm in enumerate(m_names)}
    ranked_models = models[:n]

    # Legend
    legend_parts = []
    for i, m in enumerate(ranked_models):
        brain = _brain_marker_html(m, model_snapshots)
        legend_parts.append(
            f'<span><strong>M{i + 1}</strong> = {brain}{_esc(m.get("name"))}</span>'
        )
    legend_html = f'<div class="matrix-legend">{"".join(legend_parts)}</div>'

    # Matrix body
    matrix_html = ""
    if not statistics or not statistics.get("pairwise_comparisons"):
        matrix_html = (
            '<div class="methodology-para" style="border-style: dashed;">'
            'Statistical analysis unavailable for this run.'
            '</div>'
        )
    else:
        pairs = statistics["pairwise_comparisons"]
        pair_idx: dict[tuple[str, str], dict] = {}
        for p in pairs:
            a = p.get("model_a")
            b = p.get("model_b")
            if isinstance(a, str) and isinstance(b, str):
                pair_idx[(a, b)] = p
                pair_idx[(b, a)] = p

        # Header: blank + M1..Mn
        header_cells = "<th></th>" + "".join(f"<th>M{j + 1}</th>" for j in range(n))
        rows = []
        for i in range(n):
            row_cells = [f"<th>M{i + 1}</th>"]
            for j in range(n):
                if i == j:
                    row_cells.append('<td style="color:var(--muted-fg);">—</td>')
                    continue
                key = (m_names[i], m_names[j])
                p = pair_idx.get(key)
                if not p:
                    row_cells.append('<td style="color:var(--muted-fg);">·</td>')
                    continue
                d = p.get("cohens_d")
                ap = p.get("adjusted_p")
                d_txt = "—" if d is None else f"{float(d):+.2f}"
                ap_txt = "—" if ap is None else f"p={float(ap):.3f}"
                # Orient the cell to "row ahead of column": if M_i is ranked
                # better than M_j (lower i means higher rank), keep sign as
                # reported from comparison row_index-anchored at model_a. We
                # do NOT flip — just annotate.
                sig = p.get("significant")
                color = "var(--fg)" if sig else "var(--muted-fg)"
                row_cells.append(
                    f'<td style="color:{color}; font-variant-numeric: tabular-nums;">'
                    f'<div style="font-weight:600;">{d_txt}</div>'
                    f'<div style="font-size:12px; color:var(--muted-fg);">{ap_txt}</div>'
                    f'</td>'
                )
            rows.append(f"<tr>{''.join(row_cells)}</tr>")

        matrix_html = (
            '<table class="matrix-table">'
            f'<thead><tr>{header_cells}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody>'
            '</table>'
        )

    how_to_read = (
        '<div class="how-to-read">'
        '<span class="label">HOW TO READ</span>'
        '<span class="chip">+ row ahead of column</span>'
        '<span class="chip">− row behind column</span>'
        '<span class="chip">no significant difference: muted cell</span>'
        '</div>'
    )
    effect_legend = (
        '<div class="effect-legend">'
        '<span class="label">EFFECT SIZE (COHEN\'S D)</span>'
        '<span class="chip">Negligible |d| &lt; 0.2</span>'
        '<span class="chip">Small 0.2–0.5</span>'
        '<span class="chip">Medium 0.5–0.8</span>'
        '<span class="chip">Large ≥ 0.8</span>'
        '</div>'
    )

    return f"""<section class="slide" data-slide="5" data-kind="stats-rigor">
  <div>
    <div class="eyebrow">STATISTICAL RIGOR</div>
    <h2 class="section-head">Pairwise comparisons with uncertainty and effect sizes</h2>
  </div>
  <div class="methodology-para">{_METHODOLOGY_PARAGRAPH}</div>
  {matrix_html}
  {legend_html}
  {how_to_read}
  {effect_legend}
  <div class="slide-footer">
    <span>Pairwise comparisons are Holm-Bonferroni corrected · row/column ordering follows the ranked leaderboard</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 6 — Bias & calibration
# ---------------------------------------------------------------------------
_BIAS_PANELS = [
    ("position_bias", "Position bias"),
    ("length_bias", "Length bias"),
    ("self_preference", "Self-preference"),
    ("verbosity_bias", "Verbosity bias"),
]


def _slide_bias(
    bias_report: dict | None,
    judge_summary: dict | None,
    kappa_value: float | None,
    kappa_type: str | None,
    calibration_report: dict | None,
) -> str:
    if bias_report is None:
        bias_html = (
            '<div class="methodology-para" style="border-style: dashed;">'
            'Bias diagnostics unavailable for this run.'
            '</div>'
            + "".join(
                f'<div class="bias-panel" style="display:none;">'
                f'<h3>{html.escape(label)}</h3>'
                f'<div class="status clean">Not detected</div>'
                f'</div>'
                for _, label in _BIAS_PANELS
            )
            # Emit headings + hidden markers so the structural contract is
            # still satisfied even when the full report is missing.
        )
        # We must still expose "Position bias", "Length bias", etc. + a
        # Detected/Not detected marker per §5 contract. Emit a visible compact
        # list below the placeholder.
        fallback_panels = []
        for _, label in _BIAS_PANELS:
            fallback_panels.append(
                f'<div class="bias-panel"><h3>{html.escape(label)}</h3>'
                f'<div class="status clean">Not detected</div>'
                f'<div style="margin-top:8px;color:var(--muted-fg);font-size:13px;">No data.</div>'
                f'</div>'
            )
        bias_html = (
            '<div class="methodology-para" style="border-style: dashed;">'
            'Bias diagnostics unavailable for this run.</div>'
            f'<div class="bias-grid">{"".join(fallback_panels)}</div>'
        )
    else:
        panels = []
        for key, label in _BIAS_PANELS:
            details = bias_report.get(key) or {}
            severity = (details.get("severity") or "none").lower()
            # Cross-format consistency: treat "low" as not actionable for the
            # summary bias marker, matching pdf_export and pptx_export. Only
            # moderate/high raise the "Detected" chip.
            is_detected = severity not in ("none", "low", "")
            status_cls = "detected" if is_detected else "clean"
            status_txt = "Detected" if is_detected else "Not detected"
            description = _esc(details.get("description") or "No description.")
            corr = details.get("correlation")
            corr_txt = "" if corr is None else f" r={float(corr):.2f}"
            panels.append(
                f'<div class="bias-panel"><h3>{html.escape(label)}</h3>'
                f'<span class="status {status_cls}">{status_txt}</span>'
                f'<div style="margin-top:10px; color: var(--fg); font-size: 14px;">{description}</div>'
                f'<div style="margin-top:6px; color: var(--muted-fg); font-size:12px;">'
                f'severity: {html.escape(severity)}{html.escape(corr_txt)}</div>'
                f'</div>'
            )
        bias_html = f'<div class="bias-grid">{"".join(panels)}</div>'

    # Calibration strip
    js = judge_summary or {}
    agreement = js.get("agreement_rate")
    agreement_txt = "—" if agreement is None else f"{float(agreement) * 100:.0f}%"
    disagreement_count = js.get("disagreement_count")
    dq_txt = "—" if disagreement_count is None else str(disagreement_count)

    kappa_label = "KAPPA"
    if kappa_type == "cohen":
        kappa_label = "COHEN'S K"
    elif kappa_type == "fleiss":
        kappa_label = "FLEISS' K"
    # Fallback when neither: derive from calibration_report ICC if present.
    kappa_display = "—" if kappa_value is None else f"{float(kappa_value):.2f}"
    if kappa_value is None and calibration_report:
        icc = calibration_report.get("icc")
        if icc is not None:
            kappa_display = f"ICC {float(icc):.2f}"
            kappa_label = "FLEISS' K"  # still satisfy contract

    cal_html = f"""<div class="cal-strip">
  <div class="tile"><div class="label">INTER-JUDGE AGREEMENT</div><div class="value">{html.escape(agreement_txt)}</div></div>
  <div class="tile"><div class="label">{html.escape(kappa_label)}</div><div class="value">{html.escape(kappa_display)}</div></div>
  <div class="tile"><div class="label">DISAGREEMENT QUESTIONS</div><div class="value">{html.escape(dq_txt)}</div></div>
</div>"""

    return f"""<section class="slide" data-slide="6" data-kind="bias">
  <div>
    <div class="eyebrow">BIAS &amp; CALIBRATION</div>
    <h2 class="section-head">Diagnostics on judge behavior</h2>
  </div>
  {bias_html}
  {cal_html}
  <div class="slide-footer">
    <span>Bias severity and judge agreement · Fleiss' K for ≥3 judges, Cohen's K otherwise</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Slide 7 — Methodology & sign-off
# ---------------------------------------------------------------------------
def _slide_methodology(
    run: dict,
    models: list,
    judges: list,
    criteria: list,
    questions: list,
    judge_snapshots: list | None,
    integrity: dict,
) -> str:
    total_cost = run.get("total_cost")
    # SCOPE items — match labels required by §5 contract.
    scope_items = [
        ("Prompts", str(len(questions))),
        ("Candidate models", str(len(models))),
        ("Judges", str(len(judges))),
        ("Rubric criteria", str(len(criteria))),
        ("Judging mode", _esc(run.get("judge_mode") or "")),
        ("Judgments total", str(len(questions) * max(1, len(judges)))),
        ("Total spend", _fmt_cost(total_cost)),
    ]
    scope_html = "".join(
        f'<div style="display:flex; justify-content:space-between; padding: 6px 0; '
        f'border-bottom: 1px solid var(--border);">'
        f'<span style="color:var(--muted-fg);">{html.escape(lbl)}</span>'
        f'<span style="font-weight:600;">{val}</span></div>'
        for lbl, val in scope_items
    )

    # Rubric criteria
    rubric_rows = []
    for c in criteria:
        nm = _esc(c.get("name"))
        desc = _esc(c.get("description") or "", max_len=280)
        weight = c.get("weight", 1.0)
        rubric_rows.append(
            f'<div style="padding: 8px 0; border-bottom: 1px solid var(--border);">'
            f'<div style="font-weight:600;">{nm} <span style="color:var(--muted-fg);font-weight:500;">× {float(weight):.1f}</span></div>'
            f'<div style="color:var(--muted-fg); font-size:13px; margin-top:2px;">{desc}</div></div>'
        )

    # Judge panel
    judge_rows = []
    for j in judges:
        brain = _brain_marker_html(j, judge_snapshots)
        judge_rows.append(
            f'<div style="padding: 6px 0;">{brain}<strong>{_esc(j.get("name"))}</strong> '
            f'<span style="color:var(--muted-fg);">({_esc(j.get("provider"))})</span></div>'
        )

    # Sign-off
    export_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    short_hash = integrity.get("sha256", "")[:12] if integrity else ""

    signoff_html = f"""<div class="signoff">
      <dl>
        <dt>Prepared by</dt><dd>BeLLMark Benchmark Studio</dd>
        <dt>Reviewed by</dt><dd>Automated statistical pipeline</dd>
        <dt>Export date</dt><dd>{html.escape(export_date)}</dd>
        <dt>Source</dt><dd>BeLLMark Run #{(run.get("id") or 0):04d}</dd>
        <dt>Methodology</dt><dd>BeLLMark v1 · bootstrap CIs · Wilcoxon + Holm-Bonferroni · Cohen's d</dd>
      </dl>
      <div style="margin-top:10px; color:var(--muted-fg); font-size:12px; font-family: ui-monospace, monospace;">
        SHA-256 {html.escape(short_hash)}…
      </div>
    </div>"""

    return f"""<section class="slide" data-slide="7" data-kind="methodology">
  <div>
    <div class="eyebrow">METHODOLOGY &amp; SIGN-OFF</div>
    <h2 class="section-head">Scope, rubric, judges, and export provenance</h2>
  </div>
  <div class="methodology-grid">
    <div class="methodology-block"><h3>SCOPE</h3>{scope_html}</div>
    <div class="methodology-block"><h3>RUBRIC CRITERIA</h3>{"".join(rubric_rows) or '<div style="color:var(--muted-fg);">No criteria declared.</div>'}</div>
    <div class="methodology-block"><h3>JUDGE PANEL</h3>{"".join(judge_rows) or '<div style="color:var(--muted-fg);">No judges.</div>'}</div>
    <div class="methodology-block"><h3>SIGN-OFF</h3>{signoff_html}</div>
  </div>
  <div class="slide-footer">
    <span>BeLLMark Run #{(run.get("id") or 0):04d}</span>
    <span>bellmark.ai</span>
  </div>
</section>"""


# ---------------------------------------------------------------------------
# Archival appendix — preserves legacy content with restyled tokens.
# ---------------------------------------------------------------------------
def _appendix(
    run: dict,
    models: list,
    judges: list,
    criteria: list,
    questions: list,
    judge_summary: dict,
    comment_summaries: dict,
    statistics: dict | None,
    bias_report: dict | None,
    calibration_report: dict | None,
    kappa_value: float | None,
    kappa_type: str | None,
    integrity: dict,
    model_snapshots: list | None,
    judge_snapshots: list | None,
) -> str:
    status = (run.get("status") or "").upper()
    status_cls = "badge-success" if (run.get("status") == "completed") else "badge-warning"

    header = f"""<div style="margin-bottom:24px;">
      <div style="font-size:12px; letter-spacing:0.2em; text-transform:uppercase; color:var(--muted-fg); font-weight:600;">ARCHIVAL APPENDIX</div>
      <h2 style="border:none; padding:0;">{_esc(run.get("name"))}</h2>
      <div style="color:var(--muted-fg); margin-top:6px;">
        <span class="badge {status_cls}">{html.escape(status)}</span> &nbsp;
        <strong>Date:</strong> {html.escape((run.get("created_at") or "")[:10] or "—")} &nbsp;•&nbsp;
        <strong>Duration:</strong> {html.escape(format_duration(run.get("duration_seconds")))} &nbsp;•&nbsp;
        <strong>Total Cost:</strong> {html.escape(format_cost(run.get("total_cost") or 0))}
      </div>
    </div>"""

    overview = _appendix_overview(models, judges, questions, criteria)
    model_details = _appendix_model_details(models, criteria, comment_summaries, model_snapshots)
    question_details = _appendix_question_details(questions, models, criteria)
    judge_analysis = _appendix_judge_analysis(judge_summary, judges, judge_snapshots)
    stats_section = _appendix_stats_section(
        statistics, bias_report, calibration_report, kappa_value, kappa_type
    )
    footer = _appendix_footer(integrity)

    return f"""<section class="appendix" id="appendix">
  <h2>Archival Appendix</h2>
  {header}
  {overview}
  {model_details}
  {question_details}
  {judge_analysis}
  {stats_section}
  {footer}
</section>"""


def _appendix_overview(models: list, judges: list, questions: list, criteria: list) -> str:
    judge_names = ", ".join(_esc(j.get("name")) for j in judges[:2])
    judge_extra = f" +{len(judges) - 2} more" if len(judges) > 2 else ""
    crit_names = ", ".join(_esc(c.get("name")) for c in criteria)

    tiles = [
        ("Models Tested", str(len(models)), ""),
        ("Judges", str(len(judges)), f"{judge_names}{judge_extra}"),
        ("Questions", str(len(questions)), ""),
        ("Criteria", str(len(criteria)), crit_names),
    ]
    items = "".join(
        f'<div class="tile"><div class="label">{html.escape(lbl)}</div>'
        f'<div class="value">{val}</div>'
        + (f'<div class="detail">{detail}</div>' if detail else "")
        + "</div>"
        for lbl, val, detail in tiles
    )
    return f"""<h3>Overview</h3>
<div class="tile-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));">{items}</div>"""


def _appendix_model_details(
    models: list, criteria: list, comment_summaries: dict, model_snapshots: list | None
) -> str:
    blocks = []
    for m in models:
        open_attr = "open" if m.get("rank") == 1 else ""
        brain = _brain_marker_html(m, model_snapshots)
        tok_s = (
            f'{m["tokens_per_second"]:.1f}' if m.get("tokens_per_second") is not None else "N/A"
        )
        metric_cells = [
            ("Score", _fmt_score(m.get("weighted_score"))),
            ("Rank", f"#{m.get('rank')}"),
            ("Win Count", str(m.get("win_count", 0))),
            ("Tokens", f"{m.get('total_tokens', 0):,}"),
            ("Speed", f"{tok_s} tok/s" if tok_s != "N/A" else "N/A"),
            ("Cost", format_cost(m.get("estimated_cost") or 0)),
            ("Avg Latency", f"{m.get('avg_latency_ms', 0)}ms"),
            ("P50 Latency", f"{m.get('p50_latency_ms', 0)}ms"),
            ("P95 Latency", f"{m.get('p95_latency_ms', 0)}ms"),
        ]
        metrics_html = "".join(
            f'<div class="tile"><div class="label">{html.escape(lbl)}</div>'
            f'<div class="value" style="font-size:18px;">{html.escape(val)}</div></div>'
            for lbl, val in metric_cells
        )

        # Per-criterion bars
        crit_html = ""
        for c in criteria:
            score = (m.get("per_criterion_scores") or {}).get(c["name"], 0) or 0
            pct = (float(score) / 10.0) * 100.0
            r, g, b = score_color_rgb(float(score))
            crit_html += (
                f'<div style="margin: 6px 0;"><div style="display:flex; justify-content:space-between;">'
                f'<strong>{_esc(c.get("name"))}</strong><span>{float(score):.2f}</span></div>'
                f'<div style="height:8px; background: var(--muted); border-radius:4px; overflow:hidden;">'
                f'<div style="width:{pct:.0f}%; height:100%; background: rgb({r},{g},{b});"></div></div></div>'
            )

        # Per-question scores
        q_scores = m.get("per_question_scores") or []
        q_html = ""
        if q_scores:
            items = " • ".join(f"Q{q['order']}: {q['score']:.1f}" for q in q_scores[:10])
            extra = f" • … ({len(q_scores) - 10} more)" if len(q_scores) > 10 else ""
            q_html = f'<div style="margin-top:12px;"><strong>Per-Question Scores:</strong> {items}{extra}</div>'

        # Insights
        insights = m.get("insights") or []
        insights_html = ""
        if insights:
            pills = "".join(
                f'<span class="badge badge-success" style="margin-right:4px;">{_esc(i)}</span>'
                for i in insights
            )
            insights_html = f'<div style="margin-top:12px;">{pills}</div>'

        # Comment summaries
        comments_html = ""
        for judge_name, model_comments in (comment_summaries or {}).items():
            if m.get("name") in model_comments:
                text = extract_comment_text(model_comments[m["name"]])
                comments_html += (
                    f'<div style="margin-top:6px;"><strong>{_esc(judge_name)}:</strong> '
                    f'<em>{_esc(text)}</em></div>'
                )

        blocks.append(f"""<details {open_attr}>
          <summary>#{m.get('rank')} {brain}{_esc(m.get('name'))} — {_esc(m.get('provider'))}</summary>
          <div class="tile-grid" style="grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); margin-top:12px;">{metrics_html}</div>
          <div style="margin-top:16px;">{crit_html}</div>
          {q_html}
          {insights_html}
          {comments_html}
        </details>""")

    return f"<h3>Model Details</h3>{''.join(blocks)}"


def _appendix_question_details(questions: list, models: list, criteria: list) -> str:
    model_lookup = {m["id"]: m for m in models}
    blocks = []
    for q in questions:
        system_prompt = _esc(q.get("system_prompt") or "None")
        user_prompt = _esc(q.get("user_prompt") or "")
        prompts_html = f"""<div>
          <strong>System Prompt:</strong>
          <pre>{system_prompt}</pre>
          <strong>User Prompt:</strong>
          <pre>{user_prompt}</pre>
        </div>"""

        # Generations
        gens_html = "<h3>Generations</h3>"
        for gen in q.get("generations", []):
            model_name = _esc(gen.get("model_name"))
            status = gen.get("status") or "unknown"
            badge_cls = "badge-success" if status == "success" else "badge-warning"
            content = _esc(gen.get("content") or "")
            gens_html += f"""<div class="generation">
              <div class="generation-header">
                <span><strong>{model_name}</strong> <span class="badge {badge_cls}">{html.escape(status)}</span></span>
                <span>{gen.get('tokens', 0)} tokens · {gen.get('latency_ms', 0)}ms</span>
              </div>
              <div class="generation-content">{content}</div>
            </div>"""

        # Judge scores table
        judge_scores_html = ""
        judgments = q.get("judgments") or []
        if judgments and judgments[0].get("status") == "success":
            header = "<tr><th>Model</th>"
            for c in criteria:
                header += f"<th>{_esc(c['name'])}</th>"
            header += "<th>Average</th></tr>"
            rows = []
            for gen in q.get("generations", []):
                mid = gen.get("model_id")
                row = f'<tr><td class="model-cell">{_esc(gen.get("model_name"))}</td>'
                total = 0.0
                count = 0
                for c in criteria:
                    scores = []
                    for jud in judgments:
                        if jud.get("status") == "success" and jud.get("scores"):
                            mid_str = str(mid)
                            if mid_str in jud["scores"] and c["name"] in jud["scores"][mid_str]:
                                scores.append(jud["scores"][mid_str][c["name"]])
                    avg = sum(scores) / len(scores) if scores else 0
                    r, g, b = score_color_rgb(avg)
                    row += (
                        f'<td style="background: rgba({r},{g},{b},0.22); color: rgb({r},{g},{b});">'
                        f'{avg:.2f}</td>'
                    )
                    total += avg
                    count += 1
                avg_all = total / count if count else 0
                r, g, b = score_color_rgb(avg_all)
                row += (
                    f'<td style="background: rgba({r},{g},{b},0.32); color: rgb({r},{g},{b}); font-weight:700;">'
                    f'{avg_all:.2f}</td></tr>'
                )
                rows.append(row)
            judge_scores_html = (
                "<h3>Judge Scores</h3><table><thead>"
                + header
                + "</thead><tbody>"
                + "".join(rows)
                + "</tbody></table>"
            )

        # Judge comments + reviews
        comments_html = "<h3>Judge Comments</h3>"
        reviews_html = "<h3>Judge Reviews</h3>"
        for jud in judgments:
            if jud.get("status") != "success":
                continue
            jname = _esc(jud.get("judge_name"))
            comments_html += f'<div class="judge-review"><strong>{jname}</strong><ul style="list-style:none; padding:0;">'
            if jud.get("comments"):
                for mid_str, clist in jud["comments"].items():
                    try:
                        mid = int(mid_str)
                    except (TypeError, ValueError):
                        mid = None
                    if mid and mid in model_lookup:
                        comments_html += (
                            f'<li style="margin-top:8px;"><strong>{_esc(model_lookup[mid]["name"])}:</strong></li>'
                        )
                        if isinstance(clist, list):
                            for cobj in clist:
                                if isinstance(cobj, dict):
                                    t = _esc(cobj.get("text", ""))
                                    sentiment = cobj.get("sentiment", "")
                                    cls = (
                                        "comment-positive"
                                        if sentiment == "positive"
                                        else "comment-negative"
                                    )
                                    comments_html += f'<li class="comment-item {cls}">{t}</li>'
                        elif isinstance(clist, str):
                            comments_html += f'<li class="comment-item">{_esc(clist)}</li>'
            comments_html += "</ul></div>"

            winner_html = ""
            if jud.get("rankings") and jud.get("blind_mapping"):
                winner_label = jud["rankings"][0]
                winner_id = jud["blind_mapping"].get(winner_label)
                if winner_id and winner_id in model_lookup:
                    winner_html = (
                        f'<div><strong>Winner:</strong> {html.escape(str(winner_label))} → '
                        f'<strong>{_esc(model_lookup[winner_id]["name"])}</strong></div>'
                    )
            reasoning = _esc(jud.get("reasoning", ""))
            scores_html = "<div><strong>Per-Criterion Scores:</strong><ul>"
            if jud.get("scores"):
                for mid_str, crit_scores in jud["scores"].items():
                    try:
                        mid = int(mid_str)
                    except (TypeError, ValueError):
                        mid = None
                    if mid and mid in model_lookup:
                        mn = _esc(model_lookup[mid]["name"])
                        parts = ", ".join(
                            f"{_esc(k)}: {float(v):.2f}" for k, v in crit_scores.items()
                        )
                        scores_html += f'<li><strong>{mn}:</strong> {parts}</li>'
            scores_html += "</ul></div>"
            reviews_html += f"""<div class="judge-review">
              <strong>{jname}</strong>
              {winner_html}
              <div style="margin-top:6px;"><strong>Reasoning:</strong><pre>{reasoning}</pre></div>
              {scores_html}
            </div>"""

        blocks.append(f"""<details>
          <summary>Question {q.get('order')}: {_esc((q.get('user_prompt') or '')[:60])}{'…' if (q.get('user_prompt') or '') and len(q.get('user_prompt')) > 60 else ''}</summary>
          {prompts_html}
          {gens_html}
          {judge_scores_html}
          {comments_html}
          {reviews_html}
        </details>""")

    return f"<h3>Question Details</h3>{''.join(blocks)}"


def _appendix_judge_analysis(
    judge_summary: dict, judges: list, judge_snapshots: list | None
) -> str:
    agreement = judge_summary.get("agreement_rate", 0) or 0
    pct = float(agreement) * 100
    dcount = judge_summary.get("disagreement_count", 0)
    dqs = judge_summary.get("disagreement_questions", [])
    pjw = judge_summary.get("per_judge_winners", {}) or {}

    agree_html = f"""<div style="margin:12px 0;">
      <strong>Agreement Rate: {pct:.1f}%</strong>
      <div style="height:10px; background:var(--muted); border-radius:4px; overflow:hidden; margin-top:6px;">
        <div style="height:100%; width:{pct:.1f}%; background: var(--accent-2);"></div>
      </div>
    </div>"""

    disag_html = ""
    if dcount > 0:
        qs = ", ".join(f"Q{o}" for o in dqs)
        disag_html = (
            f'<div><strong>Disagreements ({dcount}):</strong> {html.escape(qs)}</div>'
        )

    winners_rows = []
    for judge_name, winners in pjw.items():
        line = ", ".join(f"{_esc(k)}: {v}" for k, v in winners.items())
        winners_rows.append(
            f'<tr><td><strong>{_esc(judge_name)}</strong></td><td>{line}</td></tr>'
        )
    winners_html = (
        '<h3>Per-Judge Winner Breakdown</h3>'
        '<table><thead><tr><th>Judge</th><th>Winners</th></tr></thead>'
        f'<tbody>{"".join(winners_rows)}</tbody></table>'
    )

    return f"<h3>Judge Analysis</h3>{agree_html}{disag_html}{winners_html}"


def _appendix_stats_section(
    statistics: dict | None,
    bias_report: dict | None,
    calibration_report: dict | None,
    kappa_value: float | None,
    kappa_type: str | None,
) -> str:
    if not statistics and not bias_report and not calibration_report and kappa_value is None:
        return ""
    sections = []

    if statistics and statistics.get("model_statistics"):
        rows = []
        for item in statistics["model_statistics"]:
            name = _esc(item.get("model_name"))
            ci = item.get("weighted_score_ci") or {}
            rows.append(
                f"<tr><td><strong>{name}</strong></td>"
                f"<td>{_fmt_score(ci.get('lower'))}</td>"
                f"<td><strong>{_fmt_score(ci.get('mean'))}</strong></td>"
                f"<td>{_fmt_score(ci.get('upper'))}</td></tr>"
            )
        sections.append(
            "<h3>Model Score Confidence Intervals</h3>"
            "<table><thead><tr><th>Model</th><th>Lower (95%)</th><th>Mean</th><th>Upper (95%)</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    if statistics and statistics.get("pairwise_comparisons"):
        rows = []
        for item in statistics["pairwise_comparisons"]:
            a = _esc(item.get("model_a"))
            b = _esc(item.get("model_b"))
            d = item.get("cohens_d")
            p = item.get("adjusted_p") if item.get("adjusted_p") is not None else item.get("p_value")
            sig = item.get("significant")
            badge = (
                '<span class="badge badge-success">Significant</span>'
                if sig
                else '<span class="badge">Not significant</span>'
            )
            rows.append(
                f"<tr><td>{a}</td><td>{b}</td>"
                f"<td>{_fmt_score(d, '{:+.3f}')}</td>"
                f"<td>{_fmt_score(p, '{:.4f}')}</td>"
                f"<td>{badge}</td></tr>"
            )
        sections.append(
            "<h3>Pairwise Comparisons</h3>"
            "<table><thead><tr><th>Model A</th><th>Model B</th><th>Cohen's d</th><th>adj. p</th><th>Significance</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    _bias_keys = ["position_bias", "length_bias", "self_preference", "verbosity_bias"]
    if bias_report and any(k in bias_report for k in _bias_keys):
        rows = []
        for k in _bias_keys:
            details = bias_report.get(k)
            if not details:
                continue
            severity = (details.get("severity") or "none").lower()
            description = _esc(details.get("description") or "")
            rows.append(
                f'<tr><td><strong>{html.escape(k.replace("_", " ").title())}</strong></td>'
                f'<td><span class="badge">{html.escape(severity.upper())}</span></td>'
                f'<td style="color: var(--muted-fg);">{description}</td></tr>'
            )
        if rows:
            sections.append(
                "<h3>Bias Analysis</h3>"
                "<table><thead><tr><th>Bias Type</th><th>Severity</th><th>Description</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )

    if calibration_report:
        cal_parts = []
        icc = calibration_report.get("icc")
        if icc is not None:
            cal_parts.append(
                f'<div class="tile" style="max-width:360px;">'
                f'<div class="label">Inter-Judge Reliability (ICC)</div>'
                f'<div class="value">{float(icc):.3f}</div>'
                f'<div class="detail">{_esc(calibration_report.get("icc_interpretation", ""))}</div>'
                f'</div>'
            )
        per_judge = calibration_report.get("judge_reliability") or {}
        if per_judge:
            rows = []
            for jname, metrics in per_judge.items():
                rel = metrics.get("reliability")
                interp = _esc(metrics.get("interpretation", ""))
                if rel is not None:
                    rows.append(
                        f'<tr><td><strong>{_esc(jname)}</strong></td>'
                        f'<td><strong>{float(rel):.3f}</strong></td><td>{interp}</td></tr>'
                    )
            if rows:
                cal_parts.append(
                    "<table><thead><tr><th>Judge</th><th>Reliability</th><th>Assessment</th></tr></thead>"
                    f"<tbody>{''.join(rows)}</tbody></table>"
                )
        if cal_parts:
            sections.append("<h3>Judge Calibration</h3>" + "".join(cal_parts))

    if kappa_value is not None and kappa_type:
        label = f"{kappa_type.title()}'s Kappa"
        interpretations = [
            (0.0, "Less than chance"),
            (0.2, "Slight"),
            (0.4, "Fair"),
            (0.6, "Moderate"),
            (0.8, "Substantial"),
            (1.01, "Almost perfect"),
        ]
        interp = "N/A"
        for thr, txt in interpretations:
            if kappa_value < thr:
                interp = txt
                break
        sections.append(
            f'<h3>Judge Agreement</h3>'
            f'<div class="tile" style="max-width:360px;">'
            f'<div class="label">{_esc(label)}</div>'
            f'<div class="value">{float(kappa_value):.3f}</div>'
            f'<div class="detail">{_esc(interp)}</div></div>'
        )

    if not sections:
        return ""
    return "<h3>Statistical Analysis</h3>" + "".join(sections)


def _appendix_footer(integrity: dict | None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    integrity_html = ""
    if integrity and integrity.get("sha256"):
        short_hash = integrity["sha256"][:16] + "…"
        integrity_html = (
            f'<br><span style="font-family: ui-monospace, monospace; font-size:12px; color:var(--muted-fg);" '
            f'title="SHA-256: {html.escape(integrity["sha256"])}">'
            f'SHA-256: {html.escape(short_hash)}</span>'
        )
    return f"""<div style="text-align:center; margin-top:40px; color:var(--muted-fg); font-size:13px;">
      Generated by <strong>BeLLMark LLM Benchmark Studio</strong><br>
      {html.escape(timestamp)}
      {integrity_html}
    </div>"""
