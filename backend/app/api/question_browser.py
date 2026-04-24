"""Cross-benchmark question browser search endpoint."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, load_only, selectinload

from app.core.pricing import calculate_model_cost, estimate_token_split
from app.core.pricing_catalog import (
    DEFAULT_PRICE_PROVIDERS,
    MissingPricingError,
    resolve_catalog_price,
)
from app.core.question_browser import (
    QUESTION_BROWSER_MATCH_STRICT,
    calculate_question_grade,
    calculate_run_grade,
    calculate_weighted_grade,
    build_snapshot_signature,
    classify_picker_frequency_band,
    extract_model_criterion_scores,
    flatten_model_comments,
    picker_candidate_selectable,
    resolve_seed_identities,
    select_matching_generation_records,
)
from app.core.question_browser_ranking import competition_rank
from app.db.database import get_db
from app.db.models import BenchmarkRun, Generation, Judgment, ModelPreset, Question, RunStatus, TaskStatus
from app.schemas.question_browser import (
    QuestionBrowserAnswerCard,
    QuestionBrowserCardJudgeGrade,
    QuestionBrowserDetailResponse,
    QuestionBrowserMatchMode,
    QuestionBrowserPickerCandidate,
    QuestionBrowserPickerFrequencyBand,
    QuestionBrowserPickerGuidanceModel,
    QuestionBrowserPickerGuidanceResponse,
    QuestionBrowserSelectedModel,
    QuestionBrowserSearchResponse,
    QuestionBrowserSearchRow,
)

router = APIRouter(prefix="/api/question-browser", tags=["question-browser"])


_CURRENT_HOST_ALIASES = {"localhost", "127.0.0.1", "::1"}
for _host_value in {socket.gethostname(), socket.getfqdn()}:
    _normalized_host = str(_host_value or "").strip().casefold()
    if _normalized_host:
        _CURRENT_HOST_ALIASES.add(_normalized_host)
        if "." not in _normalized_host:
            _CURRENT_HOST_ALIASES.add(f"{_normalized_host}.local")


def _parse_model_ids(raw_models: str) -> list[int]:
    parts = [part.strip() for part in raw_models.split(",") if part.strip()]
    if len(parts) < 2 or len(parts) > 15:
        raise HTTPException(status_code=400, detail="models must contain 2 to 15 preset ids")

    try:
        model_ids = [int(part) for part in parts]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="models must be a comma-separated list of integers") from exc

    if len(set(model_ids)) != len(model_ids):
        raise HTTPException(status_code=400, detail="models must not contain duplicates")

    return model_ids


def _normalize_identity_text(value: Any) -> str:
    value = getattr(value, "value", value)
    text = " ".join(str(value).split()).strip()
    return text.casefold()


def _parse_optional_selected_model_ids(raw_selected_model_ids: str | None) -> list[int]:
    if raw_selected_model_ids is None:
        return []

    parts = [part.strip() for part in raw_selected_model_ids.split(",") if part.strip()]
    if not parts:
        return []

    try:
        model_ids = [int(part) for part in parts]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="selected_model_ids must be a comma-separated list of integers") from exc

    deduped_model_ids: list[int] = []
    seen_model_ids: set[int] = set()
    for model_id in model_ids:
        if model_id in seen_model_ids:
            continue
        seen_model_ids.add(model_id)
        deduped_model_ids.append(model_id)

    return deduped_model_ids


def _parse_frequency_band(raw_frequency_band: str | None) -> QuestionBrowserPickerFrequencyBand:
    normalized = (raw_frequency_band or "all").strip().casefold()
    if normalized not in {"all", "high", "medium", "low", "zero"}:
        raise HTTPException(status_code=400, detail="frequency_band must be one of all, high, medium, low, zero")
    return normalized  # type: ignore[return-value]


def _extract_host_label(base_url: Any) -> str:
    try:
        parsed = urlparse(str(base_url))
        hostname = (parsed.hostname or "").strip().casefold()
        if not hostname:
            return ""
        if hostname in _CURRENT_HOST_ALIASES:
            normalized_host = "localhost"
        else:
            try:
                if ipaddress.ip_address(hostname).is_loopback:
                    normalized_host = "localhost"
                else:
                    normalized_host = hostname
            except ValueError:
                normalized_host = hostname
        if parsed.port is not None:
            return f"{normalized_host}:{parsed.port}"
        return normalized_host
    except Exception:
        return str(base_url)


def _display_name(preset: Any) -> str:
    return str(getattr(preset, "name", "") or "")


def _preferred_visible_value(entry: Mapping[str, Any] | None, key: str, live_preset: Any | None, attr: str) -> Any:
    if entry is not None:
        entry_value = entry.get(key)
        if entry_value not in (None, ""):
            return entry_value
    live_value = getattr(live_preset, attr, None) if live_preset is not None else None
    if live_value not in (None, ""):
        return live_value
    return None


def _display_label_text(
    *,
    name: Any,
    base_url: Any,
    model_format: Any,
    quantization: Any,
    is_reasoning: Any,
    reasoning_level: Any,
) -> str:
    display_name = str(name or "")
    suffix_parts: list[str] = []
    fmt = str(model_format or "").upper().strip()
    if fmt:
        suffix_parts.append(fmt)
    quant = str(quantization or "").strip()
    if quant:
        suffix_parts.append(quant)
    host = _extract_host_label(base_url)
    if host:
        suffix_parts.append(f"@ {host}")
    if suffix_parts:
        return f"{display_name} ({' '.join(suffix_parts)})"
    return display_name


def _same_label_identity_from_entry_or_preset(
    entry: Mapping[str, Any] | None,
    live_preset: Any | None,
) -> dict[str, Any] | None:
    name = _preferred_visible_value(entry, "name", live_preset, "name")
    base_url = _preferred_visible_value(entry, "base_url", live_preset, "base_url")
    if not name or base_url is None:
        return None

    identity = {
        "display_name": _normalize_identity_text(str(name)),
        "host": _normalize_identity_text(_extract_host_label(base_url)),
    }

    model_format = _preferred_visible_value(entry, "model_format", live_preset, "model_format")
    if model_format not in (None, ""):
        identity["model_format"] = _normalize_identity_text(model_format)

    quantization = _preferred_visible_value(entry, "quantization", live_preset, "quantization")
    if quantization not in (None, ""):
        identity["quantization"] = _normalize_identity_text(quantization)

    return identity


def _same_label_identity_from_mapping(entry: Mapping[str, Any] | None) -> dict[str, Any] | None:
    identity = _same_label_identity_from_entry_or_preset(entry, None)
    if identity is None:
        return None
    identity.setdefault("reasoning_level", "")
    return identity


def _same_label_identity_from_preset(preset: Any | None) -> dict[str, Any] | None:
    return _same_label_identity_from_entry_or_preset(None, preset)


def _snapshot_entry_has_label_data(entry: Mapping[str, Any] | None) -> bool:
    if not entry:
        return False
    return bool(entry.get("name")) and entry.get("base_url") is not None


def _snapshot_identity_maps(run: BenchmarkRun | None) -> tuple[dict[int, Mapping[str, Any]], dict[int, tuple[dict[str, Any] | None, str]]]:
    if run is None:
        return {}, {}
    snapshot = run.run_config_snapshot or {}
    model_entries = snapshot.get("models", []) or []
    label_entries: dict[int, Mapping[str, Any]] = {}
    identity_map: dict[int, tuple[dict[str, Any] | None, str]] = {}
    for entry in model_entries:
        model_id = entry.get("id")
        if model_id is None:
            continue
        model_id = int(model_id)
        label_entries[model_id] = entry
        identity_map[model_id] = build_snapshot_signature(entry)
    return label_entries, identity_map


def _stable_display_label_from_entry_or_preset(
    entry: Mapping[str, Any] | None,
    live_preset: Any | None,
    model_id: int,
) -> str:
    name = _preferred_visible_value(entry, "name", live_preset, "name")
    base_url = _preferred_visible_value(entry, "base_url", live_preset, "base_url")
    model_format = _preferred_visible_value(entry, "model_format", live_preset, "model_format")
    quantization = _preferred_visible_value(entry, "quantization", live_preset, "quantization")

    if name not in (None, ""):
        return _display_label_text(
            name=name,
            base_url=base_url or "",
            model_format=model_format,
            quantization=quantization,
            is_reasoning=0,
            reasoning_level=None,
        )
    if live_preset is not None:
        model_id_value = getattr(live_preset, "model_id", None)
        if model_id_value:
            return str(model_id_value)
    if entry and entry.get("model_id"):
        return str(entry["model_id"])
    return str(model_id)


def _stable_same_label_identity_from_entry_or_preset(
    entry: Mapping[str, Any] | None,
    live_preset: Any | None,
) -> dict[str, Any] | None:
    return _same_label_identity_from_entry_or_preset(entry, live_preset)


def _build_candidate_generation_records(
    question: Question,
    *,
    run_context: Mapping[str, Any],
    match_mode: QuestionBrowserMatchMode,
) -> list[dict[str, Any]]:
    snapshot_entries = run_context["snapshot_entries"]
    snapshot_identities = run_context["snapshot_identities"]
    records: list[dict[str, Any]] = []
    for generation in question.generations:
        if generation.status != TaskStatus.success:
            continue

        candidate_identity, candidate_fidelity = snapshot_identities.get(generation.model_preset_id, (None, "degraded"))
        record = {
            "generation_id": generation.id,
            "model_preset_id": generation.model_preset_id,
            "generation": generation,
            "match_fidelity": candidate_fidelity,
            "candidate_identity": None,
            "unusable": False,
        }
        if match_mode == QUESTION_BROWSER_MATCH_STRICT:
            record["candidate_identity"] = candidate_identity
            record["unusable"] = candidate_identity is None
        else:
            record["candidate_identity"] = _stable_same_label_identity_from_entry_or_preset(
                snapshot_entries.get(generation.model_preset_id),
                generation.model_preset,
            )
            record["unusable"] = record["candidate_identity"] is None
        records.append(record)
    return records


def _load_source_run(
    *,
    db: Session,
    source_run_id: int | None,
) -> BenchmarkRun | None:
    if source_run_id is None:
        return None

    source_run = (
        db.query(BenchmarkRun)
        .filter(BenchmarkRun.id == source_run_id)
        .first()
    )
    if source_run is None:
        raise HTTPException(status_code=404, detail=f"Source run {source_run_id} not found")
    return source_run


def _resolve_selected_models(
    *,
    db: Session,
    model_ids: list[int],
    match: QuestionBrowserMatchMode,
    source_run_id: int | None,
    source_question_id: int | None,
) -> tuple[list[QuestionBrowserSelectedModel], BenchmarkRun | None]:
    source_run = _load_source_run(db=db, source_run_id=source_run_id)

    if match == QUESTION_BROWSER_MATCH_STRICT:
        if source_run is None:
            raise HTTPException(status_code=400, detail="sourceRun is required for strict mode")
        source_snapshot_entries, _ = _snapshot_identity_maps(source_run)
        try:
            selected_models = resolve_seed_identities(
                seed_model_ids=model_ids,
                match_mode=match,
                source_run_id=source_run_id,
                run=source_run,
                labels={
                    model_id: _stable_display_label_from_entry_or_preset(
                        source_snapshot_entries.get(model_id),
                        None,
                        model_id,
                    )
                    for model_id in model_ids
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return selected_models, source_run

    source_snapshot_entries = {}
    if source_run is not None:
        source_snapshot_entries, _ = _snapshot_identity_maps(source_run)

    selected_preset_map = {
        preset.id: preset
        for preset in db.query(ModelPreset)
        .filter(ModelPreset.id.in_(model_ids))
        .options(
            load_only(
                ModelPreset.id,
                ModelPreset.name,
                ModelPreset.base_url,
                ModelPreset.model_format,
                ModelPreset.quantization,
                ModelPreset.is_reasoning,
                ModelPreset.reasoning_level,
            )
        )
        .all()
    }

    selected_models = []
    missing_model_ids: list[int] = []
    for model_id in model_ids:
        source_entry = source_snapshot_entries.get(model_id) if source_run is not None else None
        live_preset = selected_preset_map.get(model_id)
        if source_entry is None and live_preset is None:
            missing_model_ids.append(model_id)
            continue

        same_label_preset = None if source_entry is not None else live_preset
        match_identity = _stable_same_label_identity_from_entry_or_preset(
            source_entry,
            same_label_preset,
        )
        if match_identity is None:
            missing_model_ids.append(model_id)
            continue

        selected_models.append(
            QuestionBrowserSelectedModel.model_validate(
                {
                    "model_preset_id": model_id,
                    "resolved_label": _stable_display_label_from_entry_or_preset(
                        source_entry,
                        same_label_preset,
                        model_id,
                    ),
                    "match_mode": match,
                    "match_identity": match_identity,
                    "match_fidelity": "full",
                    "source_run_id": source_run_id,
                    "source_question_id": source_question_id,
                }
            )
        )

    if missing_model_ids:
        raise HTTPException(status_code=400, detail=f"unknown model preset ids: {missing_model_ids}")

    return selected_models, source_run


def _build_search_response(
    *,
    selected_models,
    rows: list[dict[str, Any]],
    total_count: int,
    strict_excluded_count: int,
    initial_question_id: int | None,
    limit: int,
    offset: int,
):
    return QuestionBrowserSearchResponse(
        selected_models=selected_models,
        rows=[QuestionBrowserSearchRow.model_validate(row) for row in rows],
        total_count=total_count,
        initial_question_id=initial_question_id,
        strict_excluded_count=strict_excluded_count,
        limit=limit,
        offset=offset,
    )


def _build_prompt_preview(question: Question, limit: int = 140) -> str:
    preview = " ".join(question.user_prompt.split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 1].rstrip() + "…"


def _picker_guidance_model_payload(
    *,
    preset: ModelPreset,
    resolved_label: str,
) -> dict[str, Any]:
    reasoning_level = getattr(preset.reasoning_level, "value", preset.reasoning_level)
    return {
        "model_preset_id": preset.id,
        "name": preset.name,
        "provider": getattr(preset.provider, "value", preset.provider),
        "model_id": preset.model_id,
        "model_format": preset.model_format,
        "quantization": preset.quantization,
        "is_archived": bool(preset.is_archived),
        "is_reasoning": bool(preset.is_reasoning),
        "reasoning_level": reasoning_level,
        "resolved_label": resolved_label,
        "host_label": _extract_host_label(preset.base_url),
    }


def _picker_guidance_resolved_label(entry: Mapping[str, Any] | None, preset: Any | None) -> str:
    if entry and entry.get("name"):
        return str(entry["name"])
    if preset is not None:
        name = getattr(preset, "name", "")
        if name:
            return str(name)
        model_id = getattr(preset, "model_id", None)
        if model_id:
            return str(model_id)
        return str(getattr(preset, "id", ""))
    if entry and entry.get("model_id"):
        return str(entry["model_id"])
    return ""


@router.get("/picker-guidance", response_model=QuestionBrowserPickerGuidanceResponse)
def picker_guidance(
    selected_model_ids: str = Query("", alias="selected_model_ids", description="Comma-separated selected model preset IDs"),
    frequency_band: QuestionBrowserPickerFrequencyBand = Query("all"),
    db: Session = Depends(get_db),
):
    parsed_selected_model_ids = _parse_optional_selected_model_ids(selected_model_ids)
    requested_band = _parse_frequency_band(frequency_band)

    selected_models: list[QuestionBrowserPickerGuidanceModel] = []
    selected_identity_keys: set[tuple[tuple[str, Any], ...]] = set()
    selected_preset_map: dict[int, ModelPreset] = {}
    if parsed_selected_model_ids:
        selected_preset_map = {
            preset.id: preset
            for preset in db.query(ModelPreset)
            .filter(ModelPreset.id.in_(parsed_selected_model_ids))
            .options(
                load_only(
                    ModelPreset.id,
                    ModelPreset.name,
                    ModelPreset.provider,
                    ModelPreset.base_url,
                    ModelPreset.model_id,
                    ModelPreset.model_format,
                    ModelPreset.quantization,
                    ModelPreset.is_reasoning,
                    ModelPreset.reasoning_level,
                    ModelPreset.is_archived,
                )
            )
            .all()
        }

        for model_id in parsed_selected_model_ids:
            preset = selected_preset_map.get(model_id)
            if preset is None:
                continue
            identity = _stable_same_label_identity_from_entry_or_preset(None, preset)
            if identity is not None:
                selected_identity_keys.add(tuple(sorted(identity.items())))
            selected_models.append(
                QuestionBrowserPickerGuidanceModel.model_validate(
                    _picker_guidance_model_payload(
                        preset=preset,
                        resolved_label=_picker_guidance_resolved_label(None, preset),
                    )
                )
            )

    if len(selected_models) > 14:
        raise HTTPException(status_code=400, detail="selected_model_ids must contain at most 14 unique preset ids")

    runs = (
        db.query(BenchmarkRun)
        .options(
            load_only(BenchmarkRun.id, BenchmarkRun.name, BenchmarkRun.created_at, BenchmarkRun.run_config_snapshot),
            selectinload(BenchmarkRun.questions)
            .load_only(Question.id, Question.order)
            .selectinload(Question.generations)
            .load_only(
                Generation.id,
                Generation.question_id,
                Generation.model_preset_id,
                Generation.status,
            )
            .selectinload(Generation.model_preset)
            .load_only(
                ModelPreset.id,
                ModelPreset.name,
                ModelPreset.provider,
                ModelPreset.base_url,
                ModelPreset.model_id,
                ModelPreset.model_format,
                ModelPreset.quantization,
                ModelPreset.is_reasoning,
                ModelPreset.reasoning_level,
                ModelPreset.is_archived,
            ),
        )
        .filter(BenchmarkRun.status == RunStatus.completed)
        .order_by(BenchmarkRun.created_at.desc(), BenchmarkRun.id.desc())
        .all()
    )

    candidate_examples: dict[tuple[tuple[str, Any], ...], list[dict[str, Any]]] = {}
    candidate_run_counts: dict[tuple[tuple[str, Any], ...], int] = {}

    for run in runs:
        snapshot_entries, _ = _snapshot_identity_maps(run)
        run_all_keys: set[tuple[tuple[str, Any], ...]] = set()
        run_visible_keys: set[tuple[tuple[str, Any], ...]] = set()
        example_by_key: dict[tuple[tuple[str, Any], ...], dict[str, Any]] = {}

        for question in run.questions:
            for generation in question.generations:
                if generation.status != TaskStatus.success:
                    continue
                preset = generation.model_preset
                candidate_identity = _stable_same_label_identity_from_entry_or_preset(
                    snapshot_entries.get(generation.model_preset_id),
                    preset,
                )
                if candidate_identity is None:
                    continue
                candidate_key = tuple(sorted(candidate_identity.items()))
                run_all_keys.add(candidate_key)
                if candidate_key in selected_identity_keys:
                    continue
                run_visible_keys.add(candidate_key)
                example_by_key.setdefault(
                    candidate_key,
                    {
                        "preset": preset,
                        "resolved_label": _picker_guidance_resolved_label(
                            snapshot_entries.get(generation.model_preset_id),
                            preset,
                        ),
                    },
                )

        # Picker guidance is intentionally run-level: it answers whether models
        # appeared together in a benchmark run, not whether every matching
        # question completed successfully for that full set.
        if selected_identity_keys and not selected_identity_keys.issubset(run_all_keys):
            continue

        for candidate_key in run_visible_keys:
            candidate_run_counts[candidate_key] = candidate_run_counts.get(candidate_key, 0) + 1
        for candidate_key, example in example_by_key.items():
            candidate_examples.setdefault(candidate_key, []).append(example)

    def _pick_canonical_example(examples: list[dict[str, Any]]) -> dict[str, Any]:
        return sorted(examples, key=lambda item: (int(item["preset"].is_archived), -int(item["preset"].id)))[0]

    all_candidate_keys = set(candidate_examples)
    canonical_examples = {candidate_key: _pick_canonical_example(examples) for candidate_key, examples in candidate_examples.items()}
    max_active_count = max(candidate_run_counts.values(), default=0)
    band_counts = {"all": 0, "high": 0, "medium": 0, "low": 0, "zero": 0}
    candidate_rows: list[QuestionBrowserPickerCandidate] = []

    def _sort_key(candidate_key: tuple[tuple[str, Any], ...]) -> tuple[int, int, str]:
        example = canonical_examples[candidate_key]
        return (
            -candidate_run_counts.get(candidate_key, 0),
            int(example["preset"].is_archived),
            example["resolved_label"],
        )

    for candidate_key in sorted(all_candidate_keys, key=_sort_key):
        examples = candidate_examples.get(candidate_key, [])
        if not examples:
            continue

        canonical_example = canonical_examples[candidate_key]
        preset = canonical_example["preset"]
        active_benchmark_count = candidate_run_counts.get(candidate_key, 0)
        band = classify_picker_frequency_band(active_benchmark_count, max_active_count)
        band_counts[band] += 1
        band_counts["all"] += 1

        if requested_band != "all" and band != requested_band:
            continue

        candidate_rows.append(
            QuestionBrowserPickerCandidate.model_validate(
                {
                    **_picker_guidance_model_payload(
                        preset=preset,
                        resolved_label=canonical_example["resolved_label"],
                    ),
                    "active_benchmark_count": active_benchmark_count,
                    "selectable": picker_candidate_selectable(len(selected_models), active_benchmark_count),
                }
            )
        )

    return QuestionBrowserPickerGuidanceResponse(
        selection_state=len(selected_models),
        max_active_count=max_active_count,
        band_counts=band_counts,
        selected_models=selected_models,
        candidates=candidate_rows,
    )


@router.get("/search", response_model=QuestionBrowserSearchResponse)
def search_question_instances(
    models: str = Query(..., description="Comma-separated model preset IDs"),
    match: QuestionBrowserMatchMode = Query(QUESTION_BROWSER_MATCH_STRICT),
    source_run_id: int | None = Query(None, alias="sourceRun"),
    source_question_id: int | None = Query(None, alias="sourceQuestion"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    model_ids = _parse_model_ids(models)
    selected_models, _ = _resolve_selected_models(
        db=db,
        model_ids=model_ids,
        match=match,
        source_run_id=source_run_id,
        source_question_id=source_question_id,
    )

    if match == "same-label":
        generations_load = [
            Generation.id,
            Generation.question_id,
            Generation.model_preset_id,
            Generation.status,
        ]
        runs = (
            db.query(BenchmarkRun)
            .options(
                selectinload(BenchmarkRun.questions)
                .load_only(Question.id, Question.order, Question.user_prompt)
                .selectinload(Question.generations)
                .load_only(*generations_load)
                .selectinload(Generation.model_preset)
                .load_only(
                    ModelPreset.id,
                    ModelPreset.name,
                    ModelPreset.base_url,
                    ModelPreset.model_format,
                    ModelPreset.quantization,
                    ModelPreset.is_reasoning,
                    ModelPreset.reasoning_level,
                )
            )
            .filter(BenchmarkRun.status == RunStatus.completed)
            .order_by(BenchmarkRun.created_at.desc(), BenchmarkRun.id.desc())
            .all()
        )
    else:
        runs = (
            db.query(BenchmarkRun)
            .options(
                load_only(
                    BenchmarkRun.id,
                    BenchmarkRun.name,
                    BenchmarkRun.created_at,
                    BenchmarkRun.run_config_snapshot,
                )
            )
            .options(
                selectinload(BenchmarkRun.questions)
                .load_only(Question.id, Question.order, Question.user_prompt)
                .selectinload(Question.generations)
                .load_only(
                    Generation.id,
                    Generation.question_id,
                    Generation.model_preset_id,
                    Generation.status,
                )
            )
            .filter(BenchmarkRun.status == RunStatus.completed)
            .order_by(BenchmarkRun.created_at.desc(), BenchmarkRun.id.desc())
            .all()
        )

    matched_rows: list[dict[str, Any]] = []
    strict_excluded_run_ids: set[int] = set()
    for run in runs:
        snapshot_entries, snapshot_identities = _snapshot_identity_maps(run)
        run_context = {
            "snapshot_entries": snapshot_entries,
            "snapshot_identities": snapshot_identities,
        }
        for question in sorted(run.questions, key=lambda q: (q.order, q.id)):
            candidate_records = _build_candidate_generation_records(
                question,
                run_context=run_context,
                match_mode=match,
            )
            if len(candidate_records) < len(selected_models):
                continue

            matched_records, row_fidelity, strict_excluded = select_matching_generation_records(
                selected_models=selected_models,
                candidate_records=candidate_records,
                match_mode=match,
            )
            if matched_records is None:
                if strict_excluded:
                    strict_excluded_run_ids.add(run.id)
                continue

            matched_rows.append(
                {
                    "question_id": question.id,
                    "run_id": run.id,
                    "run_name": run.name,
                    "question_order": question.order,
                    "prompt_preview": _build_prompt_preview(question),
                    "match_fidelity": row_fidelity,
                }
            )

    total_count = len(matched_rows)
    paged_rows = matched_rows[offset : offset + limit]

    initial_question_id = source_question_id
    if initial_question_id is None or all(row["question_id"] != initial_question_id for row in matched_rows):
        initial_question_id = paged_rows[0]["question_id"] if paged_rows else None

    return _build_search_response(
        selected_models=[item.model_dump() for item in selected_models],
        rows=paged_rows,
        total_count=total_count,
        strict_excluded_count=len(strict_excluded_run_ids),
        initial_question_id=initial_question_id,
        limit=limit,
        offset=offset,
    )


def _compute_estimated_cost(generation, preset) -> float | None:
    """Compute per-generation cost in dollars. See spec decision table."""
    try:
        # --- Resolve prices per the spec contract ---
        if preset.price_input is not None and preset.price_output is not None:
            # Both overrides set: use them.
            price_in = float(preset.price_input)
            price_out = float(preset.price_output)
            cached_price = price_in
        else:
            # Either no overrides OR partial override (one set, one null):
            # ignore both and fall through to catalog.
            provider_name = getattr(preset.provider, "value", preset.provider)
            provider_key = str(provider_name).lower()
            try:
                catalog_price = resolve_catalog_price(
                    provider_name,
                    preset.model_id,
                    allow_provider_default=provider_key in DEFAULT_PRICE_PROVIDERS,
                )
                price_in = catalog_price.input_price
                price_out = catalog_price.output_price
                cached_price = catalog_price.cached_input_price
            except MissingPricingError:
                if provider_key in DEFAULT_PRICE_PROVIDERS:
                    return 0.0  # known free/local provider default
                return None  # hosted model without catalog entry

        # --- Resolve tokens per the spec decision table ---
        # Normalize non-positive split fields to None so calculate_model_cost
        # treats them as missing rather than as an actual zero.
        raw_input = getattr(generation, "input_tokens", None)
        raw_output = getattr(generation, "output_tokens", None)
        raw_cached = getattr(generation, "cached_input_tokens", None)
        total_tokens = generation.tokens

        input_tokens = raw_input if (raw_input is not None and raw_input > 0) else None
        output_tokens = raw_output if (raw_output is not None and raw_output > 0) else None
        cached_input_tokens = raw_cached if (raw_cached is not None and raw_cached > 0) else None

        total_positive = total_tokens is not None and total_tokens > 0

        # Case: no token data at all → return None.
        if input_tokens is None and output_tokens is None and not total_positive:
            return None

        # Case: both split fields are None but total is positive → let
        # calculate_model_cost trigger estimate_token_split. Otherwise the
        # helper accepts partially-populated splits and derives the missing
        # side from total_tokens when one side is known.

        provider_name = getattr(preset.provider, "value", preset.provider)
        cost, _ = calculate_model_cost(
            provider_name,
            preset.model_id,
            price_in,
            price_out,
            total_tokens=total_tokens if total_positive else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cached_input_price=cached_price,
        )
        if cost is None or cost < 0 or cost != cost:  # NaN check via self-inequality
            return None
        return float(cost)
    except Exception:
        logger.exception(
            "question_browser cost computation failed (generation_id=%s preset_id=%s provider=%s model_id=%s)",
            getattr(generation, "id", None),
            getattr(preset, "id", None),
            getattr(getattr(preset, "provider", None), "value", getattr(preset, "provider", None)),
            getattr(preset, "model_id", None),
        )
        return None


@router.get("/questions/{question_id}", response_model=QuestionBrowserDetailResponse)
def get_question_detail(
    question_id: int,
    models: str = Query(..., description="Comma-separated model preset IDs"),
    match: QuestionBrowserMatchMode = Query(QUESTION_BROWSER_MATCH_STRICT),
    source_run_id: int | None = Query(None, alias="sourceRun"),
    source_question_id: int | None = Query(None, alias="sourceQuestion"),
    db: Session = Depends(get_db),
):
    model_ids = _parse_model_ids(models)
    selected_models, _ = _resolve_selected_models(
        db=db,
        model_ids=model_ids,
        match=match,
        source_run_id=source_run_id,
        source_question_id=source_question_id,
    )

    question = (
        db.query(Question)
        .options(
            load_only(
                Question.id,
                Question.benchmark_id,
                Question.order,
                Question.system_prompt,
                Question.user_prompt,
                Question.expected_answer,
            ),
            selectinload(Question.generations)
            .load_only(
                Generation.id,
                Generation.question_id,
                Generation.model_preset_id,
                Generation.content,
                Generation.tokens,
                Generation.input_tokens,
                Generation.output_tokens,
                Generation.cached_input_tokens,
                Generation.latency_ms,
                Generation.status,
            )
            .selectinload(Generation.model_preset)
            .load_only(
                ModelPreset.id,
                ModelPreset.name,
                ModelPreset.base_url,
                ModelPreset.model_format,
                ModelPreset.quantization,
                ModelPreset.is_reasoning,
                ModelPreset.reasoning_level,
                ModelPreset.provider,
                ModelPreset.model_id,
                ModelPreset.price_input,
                ModelPreset.price_output,
            ),
            selectinload(Question.judgments)
            .load_only(
                Judgment.id,
                Judgment.question_id,
                Judgment.judge_preset_id,
                Judgment.scores,
                Judgment.reasoning,
                Judgment.comments,
                Judgment.status,
            )
            .selectinload(Judgment.judge_preset)
            .load_only(ModelPreset.id, ModelPreset.name),
        )
        .filter(Question.id == question_id)
        .first()
    )
    if question is None:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")

    run = (
        db.query(BenchmarkRun)
        .options(
            load_only(
                BenchmarkRun.id,
                BenchmarkRun.name,
                BenchmarkRun.status,
                BenchmarkRun.judge_mode,
                BenchmarkRun.criteria,
                BenchmarkRun.run_config_snapshot,
            ),
            selectinload(BenchmarkRun.questions)
            .load_only(Question.id)
            .selectinload(Question.judgments)
            .load_only(
                Judgment.id,
                Judgment.question_id,
                Judgment.scores,
                Judgment.score_rationales,
                Judgment.status,
            ),
            selectinload(BenchmarkRun.questions)
            .selectinload(Question.generations)
            .load_only(
                Generation.id,
                Generation.question_id,
                Generation.model_preset_id,
                Generation.status,
            ),
        )
        .filter(BenchmarkRun.id == question.benchmark_id)
        .first()
    )
    if run is None or run.status != RunStatus.completed:
        raise HTTPException(status_code=404, detail=f"Question {question_id} not found")

    snapshot_entries, snapshot_identities = _snapshot_identity_maps(run)
    candidate_records = _build_candidate_generation_records(
        question,
        run_context={
            "snapshot_entries": snapshot_entries,
            "snapshot_identities": snapshot_identities,
        },
        match_mode=match,
    )
    if len(candidate_records) < len(selected_models):
        raise HTTPException(status_code=404, detail=f"Question {question_id} does not match the active selection")

    matched_records, _, _ = select_matching_generation_records(
        selected_models=selected_models,
        candidate_records=candidate_records,
        match_mode=match,
    )
    if matched_records is None:
        raise HTTPException(status_code=404, detail=f"Question {question_id} does not match the active selection")

    # Collect every model that answered THIS question (across all models in run, not just selected)
    question_model_ids: set[int] = {
        gen.model_preset_id
        for gen in question.generations
        if gen.status == TaskStatus.success
    }
    # Round grades to the same 4-decimal precision used in the response so that
    # displayed grade ties produce displayed rank ties (QB-REVIEW-002).
    def _rounded(grade: float | None) -> float | None:
        return round(grade, 4) if grade is not None else None

    question_grade_by_model: dict[int, float | None] = {
        mid: _rounded(calculate_question_grade(
            question=question,
            model_preset_id=mid,
            criteria=run.criteria,
        ))
        for mid in question_model_ids
    }
    question_rank_by_model, question_rank_total = competition_rank(question_grade_by_model)

    # Collect every model that appears in the full run across all questions
    run_model_ids: set[int] = set()
    for run_question in run.questions:
        for gen in run_question.generations:
            if gen.status == TaskStatus.success:
                run_model_ids.add(gen.model_preset_id)
    run_grade_by_model: dict[int, float | None] = {
        mid: _rounded(calculate_run_grade(run=run, model_preset_id=mid))
        for mid in run_model_ids
    }
    run_rank_by_model, run_rank_total = competition_rank(run_grade_by_model)

    cards: list[QuestionBrowserAnswerCard] = []
    evaluation_mode = getattr(run.judge_mode, "value", run.judge_mode)
    for selected_model, matched_record in zip(selected_models, matched_records, strict=True):
        generation = matched_record["generation"]
        question_grade = calculate_question_grade(
            question=question,
            model_preset_id=generation.model_preset_id,
            criteria=run.criteria,
        )
        run_grade = calculate_run_grade(run=run, model_preset_id=generation.model_preset_id)

        judge_grades: list[QuestionBrowserCardJudgeGrade] = []
        judge_opinions: list[str] = []
        for judgment in question.judgments:
            if judgment.status != TaskStatus.success:
                continue

            criterion_scores = extract_model_criterion_scores(
                [judgment],
                model_preset_id=generation.model_preset_id,
            )
            comments = flatten_model_comments(
                judgment.comments,
                model_preset_id=generation.model_preset_id,
            )
            rationale_map = judgment.score_rationales or {}
            score_rationale = rationale_map.get(str(generation.model_preset_id))
            if score_rationale is None:
                score_rationale = rationale_map.get(generation.model_preset_id)
            reasoning = judgment.reasoning
            judge_score = calculate_weighted_grade(
                criteria=run.criteria,
                criterion_scores=criterion_scores,
            )
            if judge_score is None and not reasoning and not comments:
                continue

            judge_label = getattr(judgment.judge_preset, "name", str(judgment.judge_preset_id))
            judge_grades.append(
                QuestionBrowserCardJudgeGrade(
                    judge_preset_id=judgment.judge_preset_id,
                    judge_label=judge_label,
                    score=round(judge_score, 4) if judge_score is not None else None,
                    score_rationale=score_rationale,
                    reasoning=reasoning,
                    comments=comments,
                )
            )
            if reasoning:
                judge_opinions.append(f"{judge_label}: {reasoning}")
            for comment in comments:
                judge_opinions.append(f"{judge_label}: {comment}")

        speed_tokens_per_second = None
        if generation.tokens is not None and generation.latency_ms:
            speed_tokens_per_second = round(generation.tokens / (generation.latency_ms / 1000), 4)

        estimated_cost = _compute_estimated_cost(generation, generation.model_preset)
        card_question_rank = question_rank_by_model.get(generation.model_preset_id)
        card_run_rank = run_rank_by_model.get(generation.model_preset_id)

        cards.append(
            QuestionBrowserAnswerCard(
                model_preset_id=generation.model_preset_id,
                resolved_label=selected_model.resolved_label,
                source_run_id=run.id,
                source_run_name=run.name,
                evaluation_mode=evaluation_mode,
                run_grade=round(run_grade, 4) if run_grade is not None else None,
                question_grade=round(question_grade, 4) if question_grade is not None else None,
                judge_grades=judge_grades,
                tokens=generation.tokens,
                latency_ms=generation.latency_ms,
                speed_tokens_per_second=speed_tokens_per_second,
                estimated_cost=estimated_cost,
                run_rank=card_run_rank,
                run_rank_total=run_rank_total if card_run_rank is not None else None,
                question_rank=card_question_rank,
                question_rank_total=question_rank_total if card_question_rank is not None else None,
                answer_text=generation.content,
                judge_opinions=judge_opinions,
                match_fidelity=(
                    "degraded"
                    if selected_model.match_fidelity == "degraded" or matched_record["match_fidelity"] == "degraded"
                    else "full"
                ),
            )
        )

    return QuestionBrowserDetailResponse(
        question_id=question.id,
        run_id=run.id,
        run_name=run.name,
        question_order=question.order,
        system_prompt=question.system_prompt,
        user_prompt=question.user_prompt,
        expected_answer=question.expected_answer,
        selected_models=selected_models,
        cards=cards,
        source_run_id=source_run_id,
        source_question_id=source_question_id,
    )
