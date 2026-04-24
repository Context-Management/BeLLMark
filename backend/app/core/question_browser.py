"""Helpers for cross-benchmark question browser matching."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Mapping

from app.db.models import TaskStatus
from app.schemas.question_browser import (
    QuestionBrowserMatchMode,
    QuestionBrowserSelectedModel,
)

QUESTION_BROWSER_MATCH_STRICT: QuestionBrowserMatchMode = "strict"
QUESTION_BROWSER_MATCH_SAME_LABEL: QuestionBrowserMatchMode = "same-label"

STRICT_SIGNATURE_FIELDS = (
    "provider",
    "base_url",
    "model_id",
    "is_reasoning",
    "reasoning_level",
    "quantization",
    "model_format",
    "selected_variant",
    "model_architecture",
)


def build_snapshot_signature(entry: Mapping[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """Build the historical technical signature used for strict matching.

    Missing fields mark the signature as degraded; recorded fields are preserved
    exactly, including explicit ``None`` values.
    """

    if not entry:
        return None, "degraded"

    signature: dict[str, Any] = {}
    fidelity = "full"
    for field in STRICT_SIGNATURE_FIELDS:
        if field in entry:
            signature[field] = entry[field]
        else:
            fidelity = "degraded"

    if not signature:
        return None, "degraded"

    return signature, fidelity


def normalize_identity_text(value: Any) -> str:
    value = getattr(value, "value", value)
    text = " ".join(str(value).split()).strip()
    return text.casefold()


def build_label_identity(model_id: int, labels: Mapping[int, str] | None) -> str:
    """Build the canonical identity string for same-label matching."""

    if labels is None:
        labels = {}
    return normalize_identity_text(labels.get(model_id, model_id))


def _resolve_snapshot_entry(run: Any, model_id: int) -> Mapping[str, Any] | None:
    snapshot = getattr(run, "run_config_snapshot", None) or {}
    for entry in snapshot.get("models", []):
        if entry.get("id") == model_id:
            return entry
    return None


def resolve_seed_identities(
    *,
    seed_model_ids: list[int],
    match_mode: QuestionBrowserMatchMode,
    source_run_id: int | None,
    run: Any | None,
    labels: Mapping[int, str] | None,
) -> list[QuestionBrowserSelectedModel]:
    """Resolve seed model IDs into the matching identities used by the browser."""

    if match_mode != QUESTION_BROWSER_MATCH_STRICT:
        raise ValueError("resolve_seed_identities supports strict mode only")

    if source_run_id is None:
        raise ValueError("source_run_id is required for strict mode")


    if labels is None:
        labels = {}

    selected_models: list[QuestionBrowserSelectedModel] = []
    for model_id in seed_model_ids:
        resolved_label = labels.get(model_id, str(model_id))
        if run is None:
            raise ValueError("run is required to resolve strict identities")
        snapshot_entry = _resolve_snapshot_entry(run, model_id)
        if snapshot_entry is None:
            raise ValueError(f"missing strict-match snapshot for model_id {model_id}")
        identity, fidelity = build_snapshot_signature(snapshot_entry)
        if identity is None:
            raise ValueError(f"unable to derive strict-match signature for model_id {model_id}")

        selected_models.append(
            QuestionBrowserSelectedModel(
                model_preset_id=model_id,
                resolved_label=resolved_label,
                match_mode=match_mode,
                match_identity=identity,
                match_fidelity=fidelity,
                source_run_id=source_run_id,
            )
        )

    return selected_models


def strict_identity_matches(
    selected_identity: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
) -> bool:
    shared_keys = set(selected_identity).intersection(candidate_identity)
    if not shared_keys or "model_id" not in shared_keys or len(shared_keys) < 3:
        return False

    for key in shared_keys:
        if selected_identity[key] != candidate_identity[key]:
            return False
    return True


def same_label_identity_matches(
    selected_identity: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
) -> bool:
    shared_keys = set(selected_identity).intersection(candidate_identity)
    if not shared_keys:
        return False

    for key in shared_keys:
        if selected_identity[key] != candidate_identity[key]:
            return False
    return True


def classify_picker_frequency_band(active_count: int, max_active_count: int) -> str:
    if active_count <= 0 or max_active_count <= 0:
        return "zero"

    ratio = active_count / max_active_count
    if ratio >= 0.5:
        return "high"
    if ratio >= 0.2:
        return "medium"
    return "low"


def picker_candidate_selectable(selection_state: int, active_count: int) -> bool:
    return selection_state == 0 or active_count > 0


def select_matching_generation_records(
    *,
    selected_models: Sequence[QuestionBrowserSelectedModel],
    candidate_records: Sequence[Mapping[str, Any]],
    match_mode: QuestionBrowserMatchMode,
) -> tuple[list[Mapping[str, Any]] | None, str | None, bool]:
    """Match candidate generation records to the selected models in order."""

    row_fidelity = "full"
    matched_records: list[Mapping[str, Any]] = []
    used_generation_ids: set[int] = set()

    for selected_model in selected_models:
        candidate_record = None
        for record in candidate_records:
            generation_id = record.get("generation_id")
            if generation_id in used_generation_ids:
                continue
            candidate_identity = record.get("candidate_identity")
            if not isinstance(candidate_identity, Mapping):
                continue
            if match_mode == QUESTION_BROWSER_MATCH_STRICT:
                matches = strict_identity_matches(selected_model.match_identity, candidate_identity)
            else:
                matches = same_label_identity_matches(selected_model.match_identity, candidate_identity)

            if matches:
                candidate_record = record
                break

        if candidate_record is None:
            strict_excluded = (
                match_mode == QUESTION_BROWSER_MATCH_STRICT
                and any(record.get("unusable") for record in candidate_records)
            )
            return None, None, strict_excluded

        if match_mode == QUESTION_BROWSER_MATCH_STRICT and (
            selected_model.match_fidelity == "degraded"
            or candidate_record.get("match_fidelity") == "degraded"
        ):
            row_fidelity = "degraded"

        used_generation_ids.add(int(candidate_record["generation_id"]))
        matched_records.append(candidate_record)

    return matched_records, row_fidelity, False


def build_weight_map(criteria: Sequence[Mapping[str, Any]] | None) -> tuple[dict[str, float], float]:
    weight_map = {
        str(criterion["name"]): float(criterion.get("weight", 1.0))
        for criterion in (criteria or [])
        if criterion.get("name")
    }
    total_weight = sum(weight_map.values()) or 1.0
    return weight_map, total_weight


def extract_model_criterion_scores(
    judgments: Sequence[Any],
    *,
    model_preset_id: int,
) -> dict[str, list[float]]:
    criterion_scores: dict[str, list[float]] = defaultdict(list)
    score_key = str(model_preset_id)

    for judgment in judgments:
        if getattr(judgment, "status", None) != TaskStatus.success:
            continue
        scores = getattr(judgment, "scores", None) or {}
        model_scores = scores.get(score_key) or scores.get(model_preset_id)
        if not isinstance(model_scores, Mapping):
            continue
        for criterion_name, score in model_scores.items():
            if score is not None:
                criterion_scores[str(criterion_name)].append(float(score))

    return dict(criterion_scores)


def calculate_weighted_grade(
    *,
    criteria: Sequence[Mapping[str, Any]] | None,
    criterion_scores: Mapping[str, Sequence[float]] | None,
) -> float | None:
    if not criterion_scores:
        return None

    weight_map, total_weight = build_weight_map(criteria)
    weighted_sum = 0.0
    has_any = False

    for criterion in criteria or []:
        criterion_name = str(criterion["name"])
        scores = [float(score) for score in criterion_scores.get(criterion_name, []) if score is not None]
        if not scores:
            continue
        has_any = True
        weighted_sum += (sum(scores) / len(scores)) * weight_map.get(criterion_name, 1.0)

    if not has_any:
        return None
    return weighted_sum / total_weight


def calculate_question_grade(
    *,
    question: Any,
    model_preset_id: int,
    criteria: Sequence[Mapping[str, Any]] | None,
) -> float | None:
    return calculate_weighted_grade(
        criteria=criteria,
        criterion_scores=extract_model_criterion_scores(question.judgments, model_preset_id=model_preset_id),
    )


def calculate_run_grade(
    *,
    run: Any,
    model_preset_id: int,
) -> float | None:
    question_grades = [
        grade
        for question in getattr(run, "questions", [])
        if (grade := calculate_question_grade(question=question, model_preset_id=model_preset_id, criteria=run.criteria)) is not None
    ]
    if not question_grades:
        return None
    return sum(question_grades) / len(question_grades)


def flatten_model_comments(comments: Any, *, model_preset_id: int) -> list[str]:
    if not isinstance(comments, Mapping):
        return []

    raw_items = comments.get(str(model_preset_id)) or comments.get(model_preset_id) or []
    flattened: list[str] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            text = item.get("text")
            if text:
                flattened.append(str(text))
        elif item:
            flattened.append(str(item))
    return flattened
