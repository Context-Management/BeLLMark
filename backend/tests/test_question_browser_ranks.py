"""Tests for competition_rank helper and the detail-endpoint rank fields."""

import pytest

from app.core.question_browser_ranking import competition_rank


def test_competition_rank_basic_ordering():
    grades = {10: 0.9, 20: 0.5, 30: 0.7}
    ranks, total = competition_rank(grades)
    assert total == 3
    assert ranks == {10: 1, 30: 2, 20: 3}


def test_competition_rank_tie_produces_shared_rank():
    grades = {1: 0.8, 2: 0.8, 3: 0.5}
    ranks, total = competition_rank(grades)
    assert total == 3
    assert ranks[1] == 1
    assert ranks[2] == 1
    assert ranks[3] == 3  # "1224"-style skip


def test_competition_rank_three_way_tie_top():
    grades = {1: 0.7, 2: 0.7, 3: 0.7, 4: 0.3}
    ranks, total = competition_rank(grades)
    assert total == 4
    assert ranks[1] == ranks[2] == ranks[3] == 1
    assert ranks[4] == 4


def test_competition_rank_nulls_excluded():
    grades = {1: 0.8, 2: None, 3: 0.5}
    ranks, total = competition_rank(grades)
    assert total == 2
    assert ranks[1] == 1
    assert ranks[2] is None
    assert ranks[3] == 2


def test_competition_rank_all_null():
    ranks, total = competition_rank({1: None, 2: None})
    assert total == 0
    assert ranks == {1: None, 2: None}


def test_competition_rank_empty():
    ranks, total = competition_rank({})
    assert total == 0
    assert ranks == {}


# ---------- endpoint-level integration tests (Task 2.3) ----------

from datetime import datetime, timezone

import pytest

from app.api import question_browser as qb_api
from app.api.question_browser import _compute_estimated_cost
from app.db.database import get_db
from app.db.models import (
    BenchmarkRun,
    JudgeMode,
    ModelPreset,
    ProviderType,
    ReasoningLevel,
    RunStatus,
    TaskStatus,
)
from tests.test_question_browser import (
    make_completed_run,
    make_judgment,
    make_model,
    make_question_with_generations,
)


# ---------- seed helpers scoped to this file ----------

def _seed_run_with_grades(db, *, grades: list[float], provider=ProviderType.openai):
    """Seed a completed run with one question, one generation per model,
    and a single judge whose score equals the grade (criterion weight 1.0)."""
    models = [
        make_model(
            db,
            name=f"Model {idx}",
            provider=provider,
            base_url="http://x.local",
            model_id=f"m-{idx}",
        )
        for idx in range(len(grades))
    ]
    judge = make_model(
        db,
        name="Judge",
        provider=ProviderType.openai,
        base_url="http://openai.local",
        model_id="judge-1",
    )
    run = make_completed_run(
        db,
        name="Rank Test Run",
        model_presets=models,
        judge_presets=[judge],
        criteria=[{"name": "Quality", "description": "Quality", "weight": 1.0}],
    )
    question = make_question_with_generations(
        db,
        run=run,
        order=0,
        prompt="What is 2+2?",
        generation_models=models,
    )
    make_judgment(
        db,
        question=question,
        judge_preset=judge,
        scores={
            str(model.id): {"Quality": grade}
            for model, grade in zip(models, grades)
        },
    )
    db.commit()
    return run, question, models


# ---------- ranking endpoint tests ----------

def test_question_rank_total_reflects_full_run_not_subset(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(
            db, grades=[0.9, 0.7, 0.5, 0.3, 0.1]
        )
        selected = ",".join(str(m.id) for m in models[:2])
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        cards = response.json()["cards"]
        assert len(cards) == 2
        for card in cards:
            assert card["question_rank_total"] == 5
            assert card["run_rank_total"] == 5
            assert 1 <= card["question_rank"] <= 5
            assert 1 <= card["run_rank"] <= 5
    finally:
        db_gen.close()


def test_question_rank_shared_on_tie_with_skip(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(db, grades=[0.8, 0.8, 0.5])
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        ranks = {c["model_preset_id"]: c["question_rank"] for c in response.json()["cards"]}
        assert sorted(ranks.values()) == [1, 1, 3]
    finally:
        db_gen.close()


# ---------- cost endpoint tests ----------

def test_cost_endpoint_catalog_hit(client, monkeypatch):
    """Monkeypatch resolve_catalog_price to return a deterministic CatalogPrice,
    forcing the non-override catalog code path (not override, not missing)."""
    from app.core.pricing_catalog import CatalogPrice

    def _fake_resolve(provider, model_id, allow_provider_default=False, require_exact=False):
        # CatalogPrice dataclass requires all fields defined in
        # backend/app/core/pricing_catalog.py:13-23.
        return CatalogPrice(
            provider=str(provider),
            model_id=model_id,
            input_price=1.0,
            output_price=2.0,
            cached_input_price=0.5,
            currency="USD",
            pricing_mode="flat",
            source_url="https://test.local/pricing",
            checked_at="2026-04-15",
        )

    monkeypatch.setattr(qb_api, "resolve_catalog_price", _fake_resolve)

    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        # Endpoint requires 2-15 model IDs; seed 2, assert on the first card.
        run, question, models = _seed_run_with_grades(db, grades=[0.5, 0.5])
        # Generation tokens from fixture defaults: total=42, input=20, output=22
        # Cost = (20 * 1.0 + 22 * 2.0) / 1_000_000 = 6.4e-5
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        assert card["estimated_cost"] is not None
        assert abs(card["estimated_cost"] - 0.000064) < 1e-7
    finally:
        db_gen.close()


def test_cost_endpoint_unexpected_exception_returns_200_with_null(client, monkeypatch):
    def _always_raises(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(qb_api, "calculate_model_cost", _always_raises)
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(db, grades=[0.5, 0.5])
        # Force the catalog path (no override) so calculate_model_cost is the thing that fails.
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        assert card["estimated_cost"] is None
    finally:
        db_gen.close()


def test_cost_endpoint_free_local_provider_returns_zero(client):
    """LM Studio with no price override and no catalog entry → 0.0 (Free)."""
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(
            db, grades=[0.5, 0.5], provider=ProviderType.lmstudio
        )
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        assert card["estimated_cost"] == 0.0
    finally:
        db_gen.close()


def test_cost_endpoint_override_pricing_used_when_both_set(client):
    """ModelPreset.price_input + price_output override takes precedence over catalog."""
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(db, grades=[0.5, 0.5])
        models[0].price_input = 10.0
        models[0].price_output = 20.0
        db.commit()
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        # tokens from fixture: input=20, output=22 → (20*10 + 22*20) / 1e6 = 6.4e-4
        assert card["estimated_cost"] is not None
        assert abs(card["estimated_cost"] - 0.00064) < 1e-7
    finally:
        db_gen.close()


def test_cost_endpoint_tiny_precision_preserved(client):
    """Sub-$0.0001 cost must survive JSON serialization with ≥1e-6 precision."""
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        run, question, models = _seed_run_with_grades(db, grades=[0.5, 0.5])
        # price 0.05 per 1M tok, 20 input + 22 output tokens → 2.1e-6
        models[0].price_input = 0.05
        models[0].price_output = 0.05
        db.commit()
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        assert card["estimated_cost"] is not None
        assert 0 < card["estimated_cost"] < 1e-4
        assert card["estimated_cost"] >= 1e-6  # precision preserved end-to-end
    finally:
        db_gen.close()


def test_cost_endpoint_hosted_missing_catalog_returns_null(client, monkeypatch):
    from app.core.pricing_catalog import MissingPricingError

    def _always_missing(provider, model_id, allow_provider_default=False, require_exact=False):
        raise MissingPricingError(f"no entry for {provider}:{model_id}")

    monkeypatch.setattr(qb_api, "resolve_catalog_price", _always_missing)
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        # OpenAI is NOT in DEFAULT_PRICE_PROVIDERS → missing catalog → null cost
        run, question, models = _seed_run_with_grades(db, grades=[0.5, 0.5], provider=ProviderType.openai)
        selected = ",".join(str(m.id) for m in models)
        response = client.get(
            f"/api/question-browser/questions/{question.id}?models={selected}&match=same-label"
        )
        assert response.status_code == 200, response.text
        card = next(
            c for c in response.json()["cards"] if c["model_preset_id"] == models[0].id
        )
        assert card["estimated_cost"] is None
    finally:
        db_gen.close()
