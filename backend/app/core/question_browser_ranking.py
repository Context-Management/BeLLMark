"""Competition-style ranking helper for question browser grades."""

from __future__ import annotations

from typing import Iterable


def competition_rank(
    grades_by_model: dict[int, float | None],
) -> tuple[dict[int, int | None], int]:
    """Return (rank_by_model_id, total_ranked).

    - Null grades → None rank, excluded from total.
    - Equal grades share the same rank (competition "1224" style).
    - Higher grade = lower rank number (rank 1 = best).
    """

    ranked_models = [
        (model_id, grade)
        for model_id, grade in grades_by_model.items()
        if grade is not None
    ]
    ranked_models.sort(key=lambda item: item[1], reverse=True)
    total = len(ranked_models)

    rank_by_model: dict[int, int | None] = {
        model_id: None for model_id in grades_by_model
    }

    current_rank = 0
    last_grade: float | None = None
    for offset, (model_id, grade) in enumerate(ranked_models, start=1):
        if last_grade is None or grade != last_grade:
            current_rank = offset
            last_grade = grade
        rank_by_model[model_id] = current_rank

    return rank_by_model, total
