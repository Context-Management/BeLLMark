#!/usr/bin/env python3
"""One-time historical backfill for judgment score rationales."""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import selectinload

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env")

from app.core.generators import generate
from app.db.database import SessionLocal
from app.db.models import Generation, Judgment, Question, TaskStatus

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 25
DEFAULT_TEMPERATURE = 0.2


@dataclass
class BackfillStats:
    judgments_seen: int = 0
    judgments_updated: int = 0
    entries_written: int = 0
    entries_skipped: int = 0
    failures: int = 0


def _normalize_key(key: object) -> str:
    return str(key).strip()


def _normalize_score_rationales(raw: Any) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, dict):
        return {}

    normalized: dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            continue
        trimmed = str(value).strip()
        if not trimmed:
            continue
        normalized[_normalize_key(key)] = trimmed
    return normalized


def _lookup_mapping_value(mapping: Any, model_id: int) -> Any:
    if not isinstance(mapping, dict):
        return None
    return mapping.get(model_id) if model_id in mapping else mapping.get(str(model_id))


def _model_ids_for_judgment(judgment: Judgment) -> list[int]:
    if judgment.status != TaskStatus.success:
        return []

    if judgment.generation is not None:
        return [judgment.generation.model_preset_id]

    if not isinstance(judgment.scores, dict):
        return []

    model_ids: list[int] = []
    for raw_key in judgment.scores.keys():
        try:
            model_id = int(raw_key)
        except (TypeError, ValueError):
            continue
        model_ids.append(model_id)
    return sorted(set(model_ids))


def _missing_rationale_model_ids(judgment: Judgment) -> list[int]:
    existing = _normalize_score_rationales(judgment.score_rationales)
    return [model_id for model_id in _model_ids_for_judgment(judgment) if _normalize_key(model_id) not in existing]


def _truncate(text: str | None, limit: int = 4000) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _format_criterion_scores(scores: Any) -> str:
    if not isinstance(scores, dict) or not scores:
        return "None recorded."
    return "\n".join(f"- {criterion}: {score}" for criterion, score in scores.items())


def _format_comments(comments: Any) -> str:
    if not comments:
        return "None recorded."

    if isinstance(comments, list):
        lines = []
        for item in comments:
            if isinstance(item, dict):
                sentiment = item.get("sentiment", "")
                prefix = "+" if sentiment == "positive" else "-" if sentiment == "negative" else "*"
                text = item.get("text", "")
                if text:
                    lines.append(f"{prefix} {text}")
            else:
                lines.append(f"* {item}")
        return "\n".join(lines) if lines else "None recorded."

    if isinstance(comments, dict):
        lines = []
        for key, value in comments.items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines) if lines else "None recorded."

    return str(comments)


def _build_score_rationale_prompt(judgment: Judgment, target_model_id: int) -> tuple[str, str]:
    question = judgment.question
    benchmark = question.benchmark
    generation = judgment.generation

    if generation is None or generation.model_preset_id != target_model_id:
        generation = next((g for g in question.generations if g.model_preset_id == target_model_id), None)

    if generation is None:
        raise ValueError(f"Could not find generation for model {target_model_id} on judgment {judgment.id}")

    target_model_name = generation.model_preset.name if generation.model_preset else f"Model {target_model_id}"
    target_label = None
    if isinstance(judgment.blind_mapping, dict):
        for label, mid in judgment.blind_mapping.items():
            try:
                if int(mid) == target_model_id:
                    target_label = str(label).strip().upper()
                    break
            except (TypeError, ValueError):
                continue

    ranking_position = None
    if target_label and isinstance(judgment.rankings, list):
        normalized_rankings = [str(item).strip().upper() for item in judgment.rankings]
        if target_label in normalized_rankings:
            ranking_position = normalized_rankings.index(target_label) + 1

    criterion_scores = judgment.scores or {}
    if isinstance(criterion_scores, dict):
        target_scores = _lookup_mapping_value(criterion_scores, target_model_id)
    else:
        target_scores = None

    if judgment.generation is not None:
        comments = judgment.comments
    else:
        comments = _lookup_mapping_value(judgment.comments, target_model_id)

    mode_label = "comparison" if judgment.blind_mapping else "separate"
    ranking_text = (
        f"Ranked {ranking_position} of {len(judgment.rankings)}."
        if ranking_position is not None and judgment.rankings
        else ""
    )

    system_prompt = (
        "You write concise historical score rationales for BeLLMark judgments. "
        "Return only the rationale text, 1-3 sentences, with no bullets or JSON."
    )

    user_prompt = f"""
Write a concise rationale for why the judge gave this response its score.
Use only the provided judgment evidence. Do not invent new criteria or restate every comment.

Mode: {mode_label}
Judge: {judgment.judge_preset.name if judgment.judge_preset else f'Judge {judgment.judge_preset_id}'}
Question order: {question.order}

Question:
System prompt:
{_truncate(question.system_prompt, 1200)}

User prompt:
{_truncate(question.user_prompt, 2000)}

Expected answer:
{_truncate(question.expected_answer, 2000) or 'None recorded.'}

Target response:
Model: {target_model_name}
{f'Blind label: {target_label}' if target_label else ''}
{ranking_text}
Answer:
{_truncate(generation.content, 3500)}

Criterion scores for this response:
{_format_criterion_scores(target_scores)}

Raw comments for this response:
{_format_comments(comments)}

Original judge reasoning:
{_truncate(judgment.reasoning, 1500) or 'None recorded.'}
""".strip()

    return system_prompt, user_prompt


def _clean_rationale_text(content: str) -> str:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:text|markdown)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


async def _generate_score_rationale(
    judgment: Judgment,
    target_model_id: int,
    *,
    temperature: float,
) -> str:
    system_prompt, user_prompt = _build_score_rationale_prompt(judgment, target_model_id)
    result = await generate(
        judgment.judge_preset,
        system_prompt,
        user_prompt,
        temperature=temperature,
        json_mode=False,
    )
    if not result.get("success"):
        raise RuntimeError(result.get("error", "Unknown rationale generation failure"))
    content = result.get("content") or ""
    rationale = _clean_rationale_text(content)
    if not rationale:
        raise RuntimeError("Generated empty score rationale")
    return rationale


async def backfill_score_rationales(
    session,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    dry_run: bool = False,
) -> BackfillStats:
    query = (
        session.query(Judgment)
        .options(
            selectinload(Judgment.question).selectinload(Question.benchmark),
            selectinload(Judgment.question).selectinload(Question.generations).selectinload(Generation.model_preset),
            selectinload(Judgment.generation).selectinload(Generation.model_preset),
            selectinload(Judgment.judge_preset),
        )
        .filter(Judgment.status == TaskStatus.success)
        .order_by(Judgment.id)
    )
    if limit is not None:
        query = query.limit(limit)

    stats = BackfillStats()
    for judgment in query.yield_per(max(1, batch_size)):
        stats.judgments_seen += 1
        missing_model_ids = _missing_rationale_model_ids(judgment)
        if not missing_model_ids:
            stats.entries_skipped += 1
            continue

        updated = _normalize_score_rationales(judgment.score_rationales)
        wrote_any = False

        for model_id in missing_model_ids:
            try:
                rationale = await _generate_score_rationale(judgment, model_id, temperature=temperature)
            except Exception as exc:  # pragma: no cover - logged path exercised in manual runs
                stats.failures += 1
                logger.warning("Skipping rationale backfill for judgment %s model %s: %s", judgment.id, model_id, exc)
                continue

            updated[_normalize_key(model_id)] = rationale
            stats.entries_written += 1
            wrote_any = True

            if not dry_run:
                judgment.score_rationales = dict(updated)
                session.add(judgment)
                session.commit()

        if wrote_any:
            stats.judgments_updated += 1
            if dry_run:
                session.rollback()

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill historical judgment score rationales.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Number of judgments to process per batch.")
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of successful judgments to process.")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE, help="Temperature used for rationale generation.")
    parser.add_argument("--dry-run", action="store_true", help="Generate rationales without persisting changes.")
    return parser


async def main_async(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        stats = await backfill_score_rationales(
            db,
            batch_size=args.batch_size,
            limit=args.limit,
            temperature=args.temperature,
            dry_run=args.dry_run,
        )
    finally:
        db.close()

    print(f"Judgments seen: {stats.judgments_seen}")
    print(f"Judgments updated: {stats.judgments_updated}")
    print(f"Entries written: {stats.entries_written}")
    print(f"Entries skipped: {stats.entries_skipped}")
    print(f"Generation failures: {stats.failures}")
    return 1 if stats.failures else 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
