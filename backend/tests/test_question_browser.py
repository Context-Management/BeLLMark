"""Regression tests for benchmark snapshot fields used by question browser matching."""

from datetime import datetime, timezone
from importlib import util as importlib_util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect as sa_inspect
from sqlalchemy.pool import StaticPool

from app.api.question_browser import _same_label_identity_from_mapping, _parse_model_ids
from app.core.question_browser import (
    build_label_identity,
    build_snapshot_signature,
    classify_picker_frequency_band,
    resolve_seed_identities,
)
from app.db.database import get_db
from app.schemas.benchmarks import JudgmentDetail
from app.db.models import (
    BenchmarkRun,
    Generation,
    Judgment,
    JudgeMode,
    ModelPreset,
    ProviderType,
    ReasoningLevel,
    RunStatus,
    Question,
    TaskStatus,
)


def test_build_snapshot_signature_from_full_snapshot_returns_full_fidelity():
    entry = {
        "provider": "openai",
        "base_url": "http://x",
        "model_id": "gpt-4.1",
        "is_reasoning": True,
        "reasoning_level": "high",
        "quantization": None,
        "model_format": None,
        "selected_variant": "prod",
        "model_architecture": "transformer",
    }

    signature, fidelity = build_snapshot_signature(entry)

    assert fidelity == "full"
    assert signature == {
        "provider": "openai",
        "base_url": "http://x",
        "model_id": "gpt-4.1",
        "is_reasoning": True,
        "reasoning_level": "high",
        "quantization": None,
        "model_format": None,
        "selected_variant": "prod",
        "model_architecture": "transformer",
    }


def test_build_snapshot_signature_from_partial_snapshot_returns_degraded():
    entry = {"provider": "openai", "base_url": "http://x", "model_id": "gpt-4.1"}

    signature, fidelity = build_snapshot_signature(entry)

    assert fidelity == "degraded"
    assert signature == {
        "provider": "openai",
        "base_url": "http://x",
        "model_id": "gpt-4.1",
    }


def test_resolve_seed_identities_requires_source_run_for_strict_mode():
    with pytest.raises(ValueError, match="source_run_id"):
        resolve_seed_identities(
            seed_model_ids=[1, 2],
            match_mode="strict",
            source_run_id=None,
            run=None,
            labels={},
        )


def test_build_label_identity_uses_resolved_display_labels():
    labels = {1: "Claude Sonnet 7.1"}

    assert build_label_identity(1, labels) == "claude sonnet 7.1"


def test_create_benchmark_snapshot_captures_strict_signature_fields(client):
    seed_db_gen = client.app.dependency_overrides[get_db]()
    seed_db = next(seed_db_gen)
    try:
        model = ModelPreset(
            name="Claude Sonnet",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="claude-sonnet-7.1",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="sonnet",
            model_architecture="transformer",
        )
        judge = ModelPreset(
            name="GPT Judge",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="gpt-4.1",
            is_reasoning=0,
            reasoning_level=None,
            selected_variant=None,
            model_architecture=None,
        )
        seed_db.add_all([model, judge])
        seed_db.commit()
        model_id = model.id
        judge_id = judge.id

        resp = client.post("/api/benchmarks/", json={
            "name": "Snapshot Regression",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [
                {"system_prompt": "sys", "user_prompt": "What is 2+2?", "attachment_ids": []}
            ],
        })
        assert resp.status_code == 200, resp.text

        verify_db_gen = client.app.dependency_overrides[get_db]()
        verify_db = next(verify_db_gen)
        try:
            run = verify_db.query(BenchmarkRun).order_by(BenchmarkRun.id.desc()).first()
            snapshot = run.run_config_snapshot
            assert snapshot["models"][0]["is_reasoning"] == 1
            assert snapshot["models"][0]["reasoning_level"] == ReasoningLevel.high.value
            assert snapshot["models"][0]["selected_variant"] == "sonnet"
            assert snapshot["models"][0]["model_architecture"] == "transformer"
            assert snapshot["judges"][0]["is_reasoning"] == 0
            assert snapshot["judges"][0]["reasoning_level"] is None
            assert snapshot["judges"][0]["selected_variant"] is None
            assert snapshot["judges"][0]["model_architecture"] is None
            assert run.status == RunStatus.pending
        finally:
            verify_db_gen.close()
    finally:
        seed_db_gen.close()


def test_judgment_detail_preserves_score_rationales_mapping():
    detail = JudgmentDetail(
        id=1,
        judge_preset_id=2,
        judge_name="Judge",
        generation_id=None,
        blind_mapping=None,
        rankings=None,
        scores={"12": {"Quality": 8.0}},
        score_rationales={"12": "Clear and well-supported"},
        reasoning=None,
        comments=None,
        status=TaskStatus.success,
        error=None,
        retries=0,
        completed_at=None,
    )

    assert detail.score_rationales == {"12": "Clear and well-supported"}
    assert detail.model_dump()["score_rationales"] == {"12": "Clear and well-supported"}


def test_benchmark_detail_includes_score_rationales_mapping(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        question = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 5.0},
            },
            score_rationales={
                str(model_a.id): "Model A rationale",
                str(model_b.id): "Model B rationale",
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
        )
        db.commit()

        resp = client.get(f"/api/benchmarks/{run.id}")

        assert resp.status_code == 200, resp.text
        judgments = resp.json()["questions"][0]["judgments"]
        assert judgments[0]["score_rationales"] == {
            str(model_a.id): "Model A rationale",
            str(model_b.id): "Model B rationale",
        }
    finally:
        db_gen.close()


def test_benchmark_detail_returns_null_score_rationales_when_absent(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        question = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 5.0},
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
        )
        db.commit()

        resp = client.get(f"/api/benchmarks/{run.id}")

        assert resp.status_code == 200, resp.text
        judgments = resp.json()["questions"][0]["judgments"]
        assert judgments[0]["score_rationales"] is None
    finally:
        db_gen.close()


def test_question_browser_detail_includes_model_specific_score_rationale(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        question = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 5.0},
            },
            score_rationales={
                str(model_a.id): "Model A rationale",
                str(model_b.id): "Model B rationale",
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{question.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": run.id,
                "sourceQuestion": question.id,
            },
        )

        assert resp.status_code == 200, resp.text
        card = resp.json()["cards"][0]
        assert card["judge_grades"][0]["score_rationale"] == "Model A rationale"
    finally:
        db_gen.close()


def test_question_browser_detail_returns_null_score_rationale_when_absent(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        question = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 5.0},
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{question.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": run.id,
                "sourceQuestion": question.id,
            },
        )

        assert resp.status_code == 200, resp.text
        card = resp.json()["cards"][0]
        assert card["judge_grades"][0]["score_rationale"] is None

    finally:
        db_gen.close()



def test_generation_metadata_includes_question_browser_composite_index(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        inspector = sa_inspect(db.get_bind())
        indexes = inspector.get_indexes("generations")
        index = next(
            (idx for idx in indexes if idx["name"] == "ix_generations_model_preset_id_question_id"),
            None,
        )

        assert index is not None
        assert index["column_names"] == ["model_preset_id", "question_id"]
    finally:
        db_gen.close()


def test_generation_migration_creates_question_browser_composite_index():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    Table(
        "generations",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("model_preset_id", Integer, nullable=False),
        Column("question_id", Integer, nullable=False),
    )
    metadata.create_all(bind=engine)

    pre_indexes = sa_inspect(engine).get_indexes("generations")
    assert not any(idx["name"] == "ix_generations_model_preset_id_question_id" for idx in pre_indexes)

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "b1d2c3e4f5a6_add_generations_model_preset_id_question_id_index.py"
    )
    spec = importlib_util.spec_from_file_location("question_browser_generation_index_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()

    post_indexes = sa_inspect(engine).get_indexes("generations")
    index = next((idx for idx in post_indexes if idx["name"] == "ix_generations_model_preset_id_question_id"), None)
    assert index is not None
    assert index["column_names"] == ["model_preset_id", "question_id"]


def test_question_browser_factories_can_create_overlapping_runs(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        shared_model = make_model(
            db,
            name="Shared Model",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="gpt-shared",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="shared",
            model_architecture="transformer",
        )
        left_model = make_model(
            db,
            name="Left Model",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="claude-left",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="left",
            model_architecture="transformer",
        )
        right_model = make_model(
            db,
            name="Right Model",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="mistral-right",
            is_reasoning=0,
            reasoning_level=None,
            selected_variant=None,
            model_architecture=None,
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        full_snapshot = _build_snapshot(
            [shared_model, left_model],
            [judge],
        )
        degraded_snapshot = _build_snapshot(
            [shared_model, right_model],
            [judge],
            degraded=True,
        )

        left_run = make_completed_run(
            db,
            name="Left Run",
            model_presets=[shared_model, left_model],
            judge_presets=[judge],
            run_config_snapshot=full_snapshot,
        )
        right_run = make_completed_run(
            db,
            name="Right Run",
            model_presets=[shared_model, right_model],
            judge_presets=[judge],
            run_config_snapshot=degraded_snapshot,
        )

        left_question = make_question_with_generations(
            db,
            run=left_run,
            order=0,
            prompt="What is 2+2?",
            generation_models=[shared_model, left_model],
        )
        right_question = make_question_with_generations(
            db,
            run=right_run,
            order=0,
            prompt="What is 2+2?",
            generation_models=[shared_model, right_model],
        )

        make_judgment(
            db,
            question=left_question,
            judge_preset=judge,
            scores={str(shared_model.id): {"Quality": 8.0}},
            rankings=[str(shared_model.id), str(left_model.id)],
        )
        make_judgment(
            db,
            question=right_question,
            judge_preset=judge,
            scores={str(shared_model.id): {"Quality": 7.5}},
            rankings=[str(shared_model.id), str(right_model.id)],
        )

        db.commit()

        assert left_run.status == RunStatus.completed
        assert right_run.status == RunStatus.completed
        assert shared_model.id in left_run.model_ids
        assert shared_model.id in right_run.model_ids
        assert len(set(left_run.model_ids).intersection(right_run.model_ids)) == 1
        assert len(left_question.generations) == 2
        assert len(right_question.generations) == 2
        assert left_run.run_config_snapshot["models"][0]["selected_variant"] == "shared"
        assert right_run.run_config_snapshot["models"][0]["model_id"] == "gpt-shared"
        assert "reasoning_level" not in right_run.run_config_snapshot["models"][0]
    finally:
        db_gen.close()


def test_question_browser_search_returns_only_questions_with_all_selected_models(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        model_c = make_model(
            db,
            name="Model C",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="model-c",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source match question",
            generation_models=[model_a, model_b],
        )

        matching_run = make_completed_run(
            db,
            name="Matching Run",
            model_presets=[model_a, model_b, model_c],
            judge_presets=[judge],
        )
        matching_question = make_question_with_generations(
            db,
            run=matching_run,
            order=0,
            prompt="Matching question",
            generation_models=[model_a, model_b],
        )
        make_question_with_generations(
            db,
            run=matching_run,
            order=1,
            prompt="Missing one selected model",
            generation_models=[model_a],
        )

        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 2
        assert body["limit"] == 20
        assert body["offset"] == 0
        assert body["initial_question_id"] == source_question.id
        assert {row["question_id"] for row in body["rows"]} == {source_question.id, matching_question.id}
        assert all(row["question_id"] != 0 for row in body["rows"])
    finally:
        db_gen.close()


def test_question_browser_search_requires_source_run_in_strict_mode(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(db, name="Model A")
        model_b = make_model(db, name="Model B", provider=ProviderType.anthropic)
        judge = make_model(db, name="Judge", provider=ProviderType.google)
        make_completed_run(db, name="Source Run", model_presets=[model_a, model_b], judge_presets=[judge])
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 400, resp.text
    finally:
        db_gen.close()


def test_question_browser_search_paginates_results(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(db, run=source_run, order=0, prompt="Source 1", generation_models=[model_a, model_b])

        newer_run = make_completed_run(
            db,
            name="Newer Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(db, run=newer_run, order=0, prompt="Newer 1", generation_models=[model_a, model_b])
        make_question_with_generations(db, run=newer_run, order=1, prompt="Newer 2", generation_models=[model_a, model_b])

        oldest_run = make_completed_run(
            db,
            name="Oldest Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(db, run=oldest_run, order=0, prompt="Oldest 1", generation_models=[model_a, model_b])

        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
                "limit": 2,
                "offset": 2,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total_count"] == 4
        assert body["limit"] == 2
        assert body["offset"] == 2
        assert body["initial_question_id"] == body["rows"][0]["question_id"]
        assert len(body["rows"]) == 2
    finally:
        db_gen.close()


def test_question_browser_search_marks_degraded_matches(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        degraded_source_run = make_completed_run(
            db,
            name="Degraded Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
            snapshot_degraded=True,
        )
        make_question_with_generations(
            db,
            run=degraded_source_run,
            order=0,
            prompt="Degraded source question",
            generation_models=[model_a, model_b],
        )

        matching_run = make_completed_run(
            db,
            name="Matching Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=matching_run,
            order=0,
            prompt="Matching question",
            generation_models=[model_a, model_b],
        )

        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": degraded_source_run.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["rows"]
        assert body["rows"][0]["match_fidelity"] == "degraded"
        assert body["strict_excluded_count"] == 0
    finally:
        db_gen.close()


def test_question_browser_search_matches_same_label_across_different_preset_ids(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Same Label A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Same Label B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Same Label A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Same Label B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="candidate-b",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source same-label question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate same-label question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
        assert body["strict_excluded_count"] == 0
    finally:
        db_gen.close()


def test_question_browser_search_same_label_stays_stable_with_colliding_candidate_labels(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(db, name="Stable Label A", provider=ProviderType.openai, base_url="http://same.local", model_id="source-a")
        source_model_b = make_model(db, name="Stable Label B", provider=ProviderType.anthropic, base_url="http://other.local", model_id="source-b")
        candidate_model_a = make_model(db, name="Stable Label A", provider=ProviderType.openai, base_url="http://same.local", model_id="candidate-a")
        candidate_model_a_extra = make_model(db, name="Stable Label A", provider=ProviderType.openai, base_url="http://same.local", model_id="candidate-a-extra")
        candidate_model_b = make_model(db, name="Stable Label B", provider=ProviderType.anthropic, base_url="http://other.local", model_id="candidate-b")
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source collision question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_a_extra, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate collision question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
    finally:
        db_gen.close()


def test_question_browser_search_same_label_falls_back_to_live_preset_when_snapshot_labels_missing(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(db, name="Fallback Label A", provider=ProviderType.openai, base_url="http://same.local", model_id="source-a")
        source_model_b = make_model(db, name="Fallback Label B", provider=ProviderType.anthropic, base_url="http://other.local", model_id="source-b")
        candidate_model_a = make_model(db, name="Fallback Label A", provider=ProviderType.openai, base_url="http://same.local", model_id="candidate-a")
        candidate_model_b = make_model(db, name="Fallback Label B", provider=ProviderType.anthropic, base_url="http://other.local", model_id="candidate-b")
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source fallback question",
            generation_models=[source_model_a, source_model_b],
        )

        snapshot = {
            "models": [{"id": candidate_model_a.id}, {"id": candidate_model_b.id}],
            "judges": [{"id": judge.id}],
        }
        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
            run_config_snapshot=snapshot,
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate fallback question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
    finally:
        db_gen.close()


def test_question_browser_search_same_label_rejects_invalid_model_ids(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        valid_model_a = make_model(db, name="Valid A", provider=ProviderType.openai, base_url="http://same.local", model_id="valid-a")
        valid_model_b = make_model(db, name="Valid B", provider=ProviderType.anthropic, base_url="http://other.local", model_id="valid-b")
        make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{valid_model_a.id},999999",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 400, resp.text
    finally:
        db_gen.close()


def test_question_browser_search_same_label_avoids_source_side_false_positive_from_collapsed_singletons(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(db, name="Collapsed Label", provider=ProviderType.openai, base_url="http://alpha.local", model_id="source-a")
        source_model_b = make_model(db, name="Collapsed Label", provider=ProviderType.openai, base_url="http://beta.local", model_id="source-b")
        candidate_model_a = make_model(db, name="Collapsed Label", provider=ProviderType.openai, base_url="http://alpha.local", model_id="candidate-a")
        candidate_model_c = make_model(db, name="Collapsed Label", provider=ProviderType.openai, base_url="http://gamma.local", model_id="candidate-c")
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source collapsed-label question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_c],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate collapsed-label question",
            generation_models=[candidate_model_a, candidate_model_c],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id not in {row["question_id"] for row in body["rows"]}
    finally:
        db_gen.close()


def test_question_browser_search_same_label_distinguishes_cloud_provider_hosts(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Cloud Shared",
            provider=ProviderType.openai,
            base_url="https://api.openai.com/v1",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Cloud Shared",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Cloud Shared",
            provider=ProviderType.openai,
            base_url="https://api.openrouter.ai/v1",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Cloud Shared",
            provider=ProviderType.anthropic,
            base_url="https://api.openrouter.ai/v1",
            model_id="candidate-b",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source cloud-provider question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate cloud-provider question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id not in {row["question_id"] for row in body["rows"]}
    finally:
        db_gen.close()


def test_question_browser_search_same_label_normalizes_loopback_hosts(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Local Shared",
            provider=ProviderType.openai,
            base_url="http://localhost:1234/v1",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Local Shared",
            provider=ProviderType.anthropic,
            base_url="http://127.0.0.1:1234/v1",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Local Shared",
            provider=ProviderType.openai,
            base_url="http://127.0.0.1:1234/v1",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Local Shared",
            provider=ProviderType.anthropic,
            base_url="http://localhost:1234/v1",
            model_id="candidate-b",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source loopback question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate loopback question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
    finally:
        db_gen.close()


def test_question_browser_search_same_label_uses_source_run_snapshot_when_source_presets_change(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Source Stable A",
            provider=ProviderType.openai,
            base_url="https://api.openai.com/v1",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Source Stable B",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Source Stable A",
            provider=ProviderType.openai,
            base_url="https://api.openai.com/v1",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Source Stable B",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1",
            model_id="candidate-b",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source snapshot question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate snapshot question",
            generation_models=[candidate_model_a, candidate_model_b],
        )

        source_model_a.name = "Renamed Source A"
        source_model_a.base_url = "https://api.openrouter.ai/v1"
        source_model_b.name = "Renamed Source B"
        source_model_b.base_url = "https://api.openrouter.ai/v1"
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
        assert body["initial_question_id"] == source_question.id
    finally:
        db_gen.close()


def test_question_browser_search_same_label_uses_source_snapshot_when_source_presets_are_missing(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Snapshot Only A",
            provider=ProviderType.openai,
            base_url="https://api.openai.com/v1",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Snapshot Only B",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Snapshot Only A",
            provider=ProviderType.openai,
            base_url="https://api.openai.com/v1",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Snapshot Only B",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1",
            model_id="candidate-b",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source snapshot-only question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate snapshot-only question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        db.delete(source_model_a)
        db.delete(source_model_b)
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_run.model_ids[0]},{source_run.model_ids[1]}",
                "match": "same-label",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert candidate_question.id in {row["question_id"] for row in body["rows"]}
        assert [model["resolved_label"] for model in body["selected_models"]] == [
            "Snapshot Only A (@ api.openai.com)",
            "Snapshot Only B (@ api.anthropic.com)",
        ]
    finally:
        db_gen.close()


def test_question_browser_search_uses_strict_source_run_snapshot_and_returns_4xx_when_seed_missing(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        snapshot = _build_snapshot([model_a, model_b], [judge])
        snapshot["models"] = snapshot["models"][:1]
        source_run = make_completed_run(
            db,
            name="Broken Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
            run_config_snapshot=snapshot,
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Broken source question",
            generation_models=[model_a, model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 400, resp.text
    finally:
        db_gen.close()


def test_question_browser_search_surfaces_strict_exclusions_for_unusable_signatures(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        source_model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        good_model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        good_model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        broken_model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        broken_model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source strict question",
            generation_models=[source_model_a, source_model_b],
        )

        matching_run = make_completed_run(
            db,
            name="Matching Run",
            model_presets=[good_model_a, good_model_b],
            judge_presets=[judge],
        )
        matching_question = make_question_with_generations(
            db,
            run=matching_run,
            order=0,
            prompt="Matching strict question",
            generation_models=[good_model_a, good_model_b],
        )

        degraded_snapshot = _build_snapshot([broken_model_a, broken_model_b], [judge])
        degraded_snapshot["models"][1] = {
            "id": broken_model_b.id,
            "name": broken_model_b.name,
        }
        degraded_run = make_completed_run(
            db,
            name="Degraded Run",
            model_presets=[broken_model_a, broken_model_b],
            judge_presets=[judge],
            run_config_snapshot=degraded_snapshot,
        )
        make_question_with_generations(
            db,
            run=degraded_run,
            order=0,
            prompt="Degraded strict question",
            generation_models=[broken_model_a, broken_model_b],
        )
        make_question_with_generations(
            db,
            run=degraded_run,
            order=1,
            prompt="Degraded strict question 2",
            generation_models=[broken_model_a, broken_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/search",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
                "limit": 20,
                "offset": 0,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["initial_question_id"] == source_question.id
        assert {row["question_id"] for row in body["rows"]} == {source_question.id, matching_question.id}
        assert body["strict_excluded_count"] == 1
    finally:
        db_gen.close()


def test_question_browser_picker_guidance_requires_at_most_fourteen_selected_ids(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        models = []
        providers = [
            ProviderType.openai, ProviderType.anthropic, ProviderType.mistral,
            ProviderType.grok, ProviderType.openai, ProviderType.anthropic, ProviderType.mistral,
            ProviderType.grok, ProviderType.openai, ProviderType.anthropic, ProviderType.mistral,
            ProviderType.grok, ProviderType.openai, ProviderType.anthropic, ProviderType.mistral,
        ]
        for i in range(15):
            m = make_model(db, name=f"Model {i}", provider=providers[i], base_url=f"http://model{i}.local", model_id=f"model-{i}")
            models.append(m)
        db.commit()

        resp = client.get(
            "/api/question-browser/picker-guidance",
            params={
                "selected_model_ids": ",".join(str(m.id) for m in models),
            },
        )

        assert resp.status_code == 400, resp.text
        assert "at most 14" in resp.json()["detail"]
    finally:
        db_gen.close()


def test_question_browser_picker_guidance_returns_band_counts_and_selected_models(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        selected_model = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        candidate_model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
        )
        candidate_model_c = make_model(
            db,
            name="Model C",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="model-c",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run_one = make_completed_run(
            db,
            name="Run One",
            model_presets=[selected_model, candidate_model_b],
            judge_presets=[judge],
        )
        run_two = make_completed_run(
            db,
            name="Run Two",
            model_presets=[selected_model, candidate_model_c],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=run_one,
            order=0,
            prompt="Question one",
            generation_models=[selected_model, candidate_model_b],
        )
        make_question_with_generations(
            db,
            run=run_two,
            order=0,
            prompt="Question two",
            generation_models=[selected_model, candidate_model_c],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/picker-guidance",
            params={
                "selected_model_ids": f"{selected_model.id},{selected_model.id},999999",
                "frequency_band": "all",
            },
        )

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["selection_state"] == 1
        assert len(payload["selected_models"]) == 1
        assert payload["band_counts"]["all"] >= 2
        assert payload["selected_models"][0]["model_preset_id"] == selected_model.id
        assert any(candidate["active_benchmark_count"] > 0 for candidate in payload["candidates"])
    finally:
        db_gen.close()


def test_question_browser_picker_guidance_selected_models_do_not_contribute_to_candidate_metrics(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        selected_model = make_model(
            db,
            name="Shared Model",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="selected-shared",
        )
        candidate_a = make_model(
            db,
            name="Candidate A",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="candidate-a",
        )
        candidate_b = make_model(
            db,
            name="Candidate B",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="candidate-b",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run_one = make_completed_run(db, name="Run One", model_presets=[selected_model, candidate_a], judge_presets=[judge])
        run_two = make_completed_run(db, name="Run Two", model_presets=[selected_model, candidate_a], judge_presets=[judge])
        run_three = make_completed_run(db, name="Run Three", model_presets=[selected_model, candidate_b], judge_presets=[judge])
        run_four = make_completed_run(db, name="Run Four", model_presets=[selected_model], judge_presets=[judge])
        make_question_with_generations(db, run=run_one, order=0, prompt="Question one", generation_models=[selected_model, candidate_a])
        make_question_with_generations(db, run=run_two, order=0, prompt="Question two", generation_models=[selected_model, candidate_a])
        make_question_with_generations(db, run=run_three, order=0, prompt="Question three", generation_models=[selected_model, candidate_b])
        make_question_with_generations(db, run=run_four, order=0, prompt="Question four", generation_models=[selected_model])
        db.commit()

        resp = client.get(
            "/api/question-browser/picker-guidance",
            params={
                "selected_model_ids": str(selected_model.id),
                "frequency_band": "all",
            },
        )

        assert resp.status_code == 200, resp.text
        payload = resp.json()
        candidate_counts = {candidate["resolved_label"]: candidate["active_benchmark_count"] for candidate in payload["candidates"]}
        assert payload["selection_state"] == 1
        assert payload["max_active_count"] == 2
        assert payload["band_counts"] == {"all": 2, "high": 2, "medium": 0, "low": 0, "zero": 0}
        assert candidate_counts == {"Candidate A": 2, "Candidate B": 1}
    finally:
        db_gen.close()


def test_question_browser_picker_guidance_ignores_candidates_from_nonmatching_runs(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        selected_model = make_model(
            db,
            name="Seed Model",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="seed-model",
        )
        matching_candidate = make_model(
            db,
            name="Matching Candidate",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="matching-candidate",
        )
        unrelated_model = make_model(
            db,
            name="Unrelated Model",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="unrelated-model",
        )
        stray_candidate = make_model(
            db,
            name="Stray Candidate",
            provider=ProviderType.grok,
            base_url="http://grok.local",
            model_id="stray-candidate",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        matching_run = make_completed_run(
            db,
            name="Matching Run",
            model_presets=[selected_model, matching_candidate],
            judge_presets=[judge],
        )
        nonmatching_run = make_completed_run(
            db,
            name="Nonmatching Run",
            model_presets=[unrelated_model, stray_candidate],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=matching_run,
            order=0,
            prompt="Matching question",
            generation_models=[selected_model, matching_candidate],
        )
        make_question_with_generations(
            db,
            run=nonmatching_run,
            order=0,
            prompt="Nonmatching question",
            generation_models=[unrelated_model, stray_candidate],
        )
        db.commit()

        response = client.get(
            "/api/question-browser/picker-guidance",
            params={
                "selected_model_ids": str(selected_model.id),
                "frequency_band": "all",
            },
        )

        assert response.status_code == 200, response.text
        names = [candidate["resolved_label"] for candidate in response.json()["candidates"]]
        assert names == ["Matching Candidate"]
    finally:
        db_gen.close()


def test_question_browser_picker_guidance_defaults_missing_frequency_band_to_all(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        selected_model = make_model(
            db,
            name="GPT-OSS 120B",
            provider=ProviderType.lmstudio,
            base_url="http://localhost:1234/v1/chat/completions",
            model_id="openai/gpt-oss-120b",
            is_reasoning=1,
            reasoning_level=None,
        )
        selected_model.model_format = "GGUF"
        selected_model.quantization = "MXFP4"
        candidate_model = make_model(
            db,
            name="Claude Opus 4.6 [Reasoning (high)]",
            provider=ProviderType.anthropic,
            base_url="https://api.anthropic.com/v1/messages",
            model_id="claude-opus-4-6",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
        )
        judge = make_model(db, name="Judge", provider=ProviderType.google, base_url="http://google.local", model_id="judge-1")

        run = make_completed_run(db, name="Run One", model_presets=[selected_model, candidate_model], judge_presets=[judge])
        make_question_with_generations(db, run=run, order=0, prompt="Question one", generation_models=[selected_model, candidate_model])
        db.commit()

        response = client.get('/api/question-browser/picker-guidance', params={"selected_model_ids": str(selected_model.id)})

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["selection_state"] == 1
        assert any(candidate["resolved_label"] == "Claude Opus 4.6 [Reasoning (high)]" for candidate in payload["candidates"])
    finally:
        db_gen.close()


def test_picker_guidance_band_thresholds_follow_plan_semantics():
    assert classify_picker_frequency_band(0, 10) == "zero"
    assert classify_picker_frequency_band(10, 10) == "high"
    assert classify_picker_frequency_band(5, 10) == "high"
    assert classify_picker_frequency_band(2, 10) == "medium"
    assert classify_picker_frequency_band(1, 10) == "low"
    assert classify_picker_frequency_band(1, 0) == "zero"


def test_same_label_identity_from_mapping_omits_missing_is_reasoning():
    identity = _same_label_identity_from_mapping(
        {
            "name": "Legacy Model",
            "base_url": "http://legacy.local",
            "model_format": "gguf",
            "quantization": "Q4_K_M",
        }
    )

    assert identity is not None
    assert "is_reasoning" not in identity
    assert identity["reasoning_level"] == ""


def test_question_browser_picker_guidance_same_label_deduplicates_candidates(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        selected_model = make_model(
            db,
            name="GPT-OSS 120B",
            provider=ProviderType.lmstudio,
            base_url="http://localhost:1234/v1/chat/completions",
            model_id="selected-oss",
            is_reasoning=1,
            reasoning_level=None,
        )
        candidate_model_a = make_model(
            db,
            name="GPT-OSS 120B",
            provider=ProviderType.lmstudio,
            base_url="http://localhost:1234/v1/chat/completions",
            model_id="candidate-oss-a",
            is_reasoning=1,
            reasoning_level=None,
        )
        candidate_model_b = make_model(
            db,
            name="GPT-OSS 120B",
            provider=ProviderType.lmstudio,
            base_url="http://localhost:1234/v1/chat/completions",
            model_id="candidate-oss-b",
            is_reasoning=1,
            reasoning_level=None,
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run_one = make_completed_run(
            db,
            name="Run One",
            model_presets=[selected_model, candidate_model_a],
            judge_presets=[judge],
        )
        run_two = make_completed_run(
            db,
            name="Run Two",
            model_presets=[selected_model, candidate_model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=run_one,
            order=0,
            prompt="Question one",
            generation_models=[selected_model, candidate_model_a],
        )
        make_question_with_generations(
            db,
            run=run_two,
            order=0,
            prompt="Question two",
            generation_models=[selected_model, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            "/api/question-browser/picker-guidance",
            params={
                "selected_model_ids": "",
                "frequency_band": "all",
            },
        )

        names = [candidate["resolved_label"] for candidate in resp.json()["candidates"]]
        assert names.count("GPT-OSS 120B") == 1
    finally:
        db_gen.close()


def test_question_browser_detail_returns_only_selected_model_cards(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        model_c = make_model(
            db,
            name="Model C",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="model-c",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source question",
            generation_models=[model_a, model_b],
        )

        matching_run = make_completed_run(
            db,
            name="Matching Run",
            model_presets=[model_a, model_b, model_c],
            judge_presets=[judge],
        )
        matching_question = make_question_with_generations(
            db,
            run=matching_run,
            order=0,
            prompt="Matching question",
            generation_models=[model_a, model_b, model_c],
        )
        make_judgment(
            db,
            question=matching_question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 7.0},
                str(model_c.id): {"Quality": 6.0},
            },
            rankings=["A", "B", "C"],
            blind_mapping={"A": model_a.id, "B": model_b.id, "C": model_c.id},
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{matching_question.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_run_id"] == source_run.id
        assert body["source_question_id"] == source_question.id
        assert [card["model_preset_id"] for card in body["cards"]] == [model_a.id, model_b.id]
        assert {card["source_run_id"] for card in body["cards"]} == {matching_run.id}
        assert all(card["source_run_name"] == "Matching Run" for card in body["cards"])
    finally:
        db_gen.close()


def test_question_browser_detail_same_label_cards_use_matched_candidate_model_ids(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        source_model_a = make_model(
            db,
            name="Detail Same Label A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="source-a",
        )
        source_model_b = make_model(
            db,
            name="Detail Same Label B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="source-b",
        )
        candidate_model_a = make_model(
            db,
            name="Detail Same Label A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="candidate-a",
        )
        candidate_model_b = make_model(
            db,
            name="Detail Same Label B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="candidate-b",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[source_model_a, source_model_b],
            judge_presets=[judge],
        )
        source_question = make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source detail same-label question",
            generation_models=[source_model_a, source_model_b],
        )

        candidate_run = make_completed_run(
            db,
            name="Candidate Run",
            model_presets=[candidate_model_a, candidate_model_b],
            judge_presets=[judge],
        )
        candidate_question = make_question_with_generations(
            db,
            run=candidate_run,
            order=0,
            prompt="Candidate detail same-label question",
            generation_models=[candidate_model_a, candidate_model_b],
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{candidate_question.id}",
            params={
                "models": f"{source_model_a.id},{source_model_b.id}",
                "match": "same-label",
                "sourceRun": source_run.id,
                "sourceQuestion": source_question.id,
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert [card["model_preset_id"] for card in body["cards"]] == [candidate_model_a.id, candidate_model_b.id]
        assert [model["model_preset_id"] for model in body["selected_models"]] == [source_model_a.id, source_model_b.id]
    finally:
        db_gen.close()


def test_question_browser_detail_includes_question_and_run_grades(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
            criteria=[
                {"name": "Quality", "description": "Quality", "weight": 3.0},
                {"name": "Style", "description": "Style", "weight": 1.0},
            ],
        )
        question_one = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        question_two = make_question_with_generations(
            db,
            run=run,
            order=1,
            prompt="Question two",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question_one,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0, "Style": 6.0},
                str(model_b.id): {"Quality": 5.0, "Style": 5.0},
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
            reasoning="Model A is stronger overall.",
            comments={
                str(model_a.id): [{"text": "Strong structure"}],
                str(model_b.id): [{"text": "Adequate"}],
            },
        )
        make_judgment(
            db,
            question=question_two,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 4.0, "Style": 4.0},
                str(model_b.id): {"Quality": 7.0, "Style": 7.0},
            },
            rankings=["B", "A"],
            blind_mapping={"A": model_b.id, "B": model_a.id},
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{question_one.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": run.id,
                "sourceQuestion": question_one.id,
            },
        )

        assert resp.status_code == 200, resp.text
        cards = {card["model_preset_id"]: card for card in resp.json()["cards"]}
        assert cards[model_a.id]["evaluation_mode"] == "comparison"
        assert cards[model_a.id]["question_grade"] == pytest.approx(7.5)
        assert cards[model_a.id]["run_grade"] == pytest.approx(5.75)
        assert cards[model_a.id]["judge_grades"][0]["score"] == pytest.approx(7.5)
        assert "score_rationale" in cards[model_a.id]["judge_grades"][0]
        assert cards[model_b.id]["question_grade"] == pytest.approx(5.0)
        assert cards[model_b.id]["run_grade"] == pytest.approx(6.0)
    finally:
        db_gen.close()


def test_question_browser_detail_includes_score_rationale_field(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        run = make_completed_run(
            db,
            name="Scored Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        question = make_question_with_generations(
            db,
            run=run,
            order=0,
            prompt="Question one",
            generation_models=[model_a, model_b],
        )
        make_judgment(
            db,
            question=question,
            judge_preset=judge,
            scores={
                str(model_a.id): {"Quality": 8.0},
                str(model_b.id): {"Quality": 5.0},
            },
            rankings=["A", "B"],
            blind_mapping={"A": model_a.id, "B": model_b.id},
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{question.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": run.id,
                "sourceQuestion": question.id,
            },
        )

        assert resp.status_code == 200, resp.text
        card = resp.json()["cards"][0]
        assert "score_rationale" in card["judge_grades"][0]
    finally:
        db_gen.close()


def test_question_browser_detail_rejects_non_matching_question(client):
    db_gen = client.app.dependency_overrides[get_db]()
    db = next(db_gen)
    try:
        model_a = make_model(
            db,
            name="Model A",
            provider=ProviderType.openai,
            base_url="http://openai.local",
            model_id="model-a",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.high,
            selected_variant="a",
            model_architecture="transformer",
        )
        model_b = make_model(
            db,
            name="Model B",
            provider=ProviderType.anthropic,
            base_url="http://anthropic.local",
            model_id="model-b",
            is_reasoning=1,
            reasoning_level=ReasoningLevel.medium,
            selected_variant="b",
            model_architecture="transformer",
        )
        model_c = make_model(
            db,
            name="Model C",
            provider=ProviderType.mistral,
            base_url="http://mistral.local",
            model_id="model-c",
        )
        judge = make_model(
            db,
            name="Judge",
            provider=ProviderType.google,
            base_url="http://google.local",
            model_id="judge-1",
        )

        source_run = make_completed_run(
            db,
            name="Source Run",
            model_presets=[model_a, model_b],
            judge_presets=[judge],
        )
        make_question_with_generations(
            db,
            run=source_run,
            order=0,
            prompt="Source question",
            generation_models=[model_a, model_b],
        )

        non_matching_run = make_completed_run(
            db,
            name="Non Matching Run",
            model_presets=[model_a, model_c],
            judge_presets=[judge],
        )
        non_matching_question = make_question_with_generations(
            db,
            run=non_matching_run,
            order=0,
            prompt="Missing selected model B",
            generation_models=[model_a, model_c],
        )
        db.commit()

        resp = client.get(
            f"/api/question-browser/questions/{non_matching_question.id}",
            params={
                "models": f"{model_a.id},{model_b.id}",
                "match": "strict",
                "sourceRun": source_run.id,
            },
        )

        assert resp.status_code == 404, resp.text
    finally:
        db_gen.close()



def make_model(
    db,
    name,
    *,
    provider=ProviderType.openai,
    base_url="http://x",
    model_id="m",
    is_reasoning=False,
    reasoning_level=None,
    selected_variant=None,
    model_architecture=None,
):
    model = ModelPreset(
        name=name,
        provider=provider,
        base_url=base_url,
        model_id=model_id,
        is_reasoning=int(bool(is_reasoning)),
        reasoning_level=reasoning_level,
        selected_variant=selected_variant,
        model_architecture=model_architecture,
    )
    db.add(model)
    db.flush()
    return model


def _snapshot_entry(
    model,
    *,
    degraded=False,
    include_fields=None,
    omit_fields=None,
    overrides=None,
):
    data = {
        "id": model.id,
        "name": model.name,
        "provider": model.provider.value if hasattr(model.provider, "value") else model.provider,
        "base_url": model.base_url,
        "model_id": model.model_id,
    }
    if not degraded:
        data["is_reasoning"] = int(bool(model.is_reasoning))
        data["reasoning_level"] = model.reasoning_level.value if model.reasoning_level else None
        data["selected_variant"] = model.selected_variant
        data["model_architecture"] = model.model_architecture

    if include_fields is not None:
        allowed = {"id", "name", "provider", "base_url", "model_id", *include_fields}
        data = {key: value for key, value in data.items() if key in allowed}

    if omit_fields is not None:
        data = {key: value for key, value in data.items() if key not in set(omit_fields)}

    if overrides:
        data.update(overrides)

    return data


def _build_snapshot(
    models,
    judges,
    *,
    degraded=False,
    model_overrides=None,
    judge_overrides=None,
):
    model_overrides = model_overrides or {}
    judge_overrides = judge_overrides or {}
    return {
        "models": [
            _snapshot_entry(
                model,
                degraded=degraded,
                overrides=model_overrides.get(model.id),
            )
            for model in models
        ],
        "judges": [
            _snapshot_entry(
                judge,
                degraded=degraded,
                overrides=judge_overrides.get(judge.id),
            )
            for judge in judges
        ],
    }


def make_completed_run(
    db,
    *,
    name,
    model_presets,
    judge_presets,
    run_config_snapshot=None,
    snapshot_degraded=False,
    snapshot_model_overrides=None,
    snapshot_judge_overrides=None,
    criteria=None,
    judge_mode=JudgeMode.comparison,
    status=RunStatus.completed,
    completed_at=None,
):
    run = BenchmarkRun(
        name=name,
        status=status,
        judge_mode=judge_mode,
        criteria=criteria or [{"name": "Quality", "description": "Quality", "weight": 1.0}],
        model_ids=[model.id for model in model_presets],
        judge_ids=[judge.id for judge in judge_presets],
        completed_at=completed_at if completed_at is not None else datetime.now(timezone.utc),
        run_config_snapshot=run_config_snapshot
        if run_config_snapshot is not None
        else _build_snapshot(
            model_presets,
            judge_presets,
            degraded=snapshot_degraded,
            model_overrides=snapshot_model_overrides,
            judge_overrides=snapshot_judge_overrides,
        ),
    )
    db.add(run)
    db.flush()
    return run


def make_question_with_generations(
    db,
    *,
    run,
    order,
    prompt,
    generation_models,
    system_prompt="sys",
    expected_answer=None,
    content_factory=None,
    tokens=42,
    input_tokens=20,
    output_tokens=22,
    cached_input_tokens=None,
    reasoning_tokens=None,
    raw_chars=None,
    answer_chars=None,
    latency_ms=1000,
    status=TaskStatus.success,
    error=None,
    retries=0,
    started_at=None,
    completed_at=None,
    model_version=None,
):
    question = Question(
        benchmark_id=run.id,
        order=order,
        system_prompt=system_prompt,
        user_prompt=prompt,
        expected_answer=expected_answer,
    )
    db.add(question)
    db.flush()

    for model in generation_models:
        generation = Generation(
            question_id=question.id,
            model_preset_id=model.id,
            content=content_factory(model) if content_factory else f"Answer from {model.name}",
            tokens=tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            reasoning_tokens=reasoning_tokens,
            raw_chars=raw_chars,
            answer_chars=answer_chars,
            latency_ms=latency_ms,
            status=status,
            error=error,
            retries=retries,
            started_at=started_at,
            completed_at=completed_at if completed_at is not None else datetime.now(timezone.utc),
            model_version=model_version,
        )
        db.add(generation)

    db.flush()
    return question


def make_judgment(
    db,
    *,
    question,
    judge_preset,
    scores,
    rankings=None,
    blind_mapping=None,
    presentation_mapping=None,
    reasoning=None,
    comments=None,
    score_rationales=None,
    latency_ms=1000,
    tokens=25,
    input_tokens=10,
    output_tokens=15,
    cached_input_tokens=None,
    reasoning_tokens=None,
    status=TaskStatus.success,
    error=None,
    retries=0,
    completed_at=None,
    judge_temperature=None,
    generation=None,
):
    judgment = Judgment(
        question_id=question.id,
        judge_preset_id=judge_preset.id,
        generation_id=generation.id if generation else None,
        blind_mapping=blind_mapping or {},
        presentation_mapping=presentation_mapping,
        rankings=rankings,
        scores=scores,
        reasoning=reasoning,
        comments=comments,
        score_rationales=score_rationales,
        latency_ms=latency_ms,
        tokens=tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_input_tokens,
        reasoning_tokens=reasoning_tokens,
        status=status,
        error=error,
        retries=retries,
        completed_at=completed_at if completed_at is not None else datetime.now(timezone.utc),
        judge_temperature=judge_temperature,
    )
    db.add(judgment)
    db.flush()
    return judgment


def test_parse_model_ids_accepts_five():
    result = _parse_model_ids("1,2,3,4,5")
    assert result == [1, 2, 3, 4, 5]


def test_parse_model_ids_accepts_fifteen():
    ids = ",".join(str(i) for i in range(1, 16))
    result = _parse_model_ids(ids)
    assert len(result) == 15


def test_parse_model_ids_rejects_sixteen():
    ids = ",".join(str(i) for i in range(1, 17))
    with pytest.raises(Exception) as exc_info:
        _parse_model_ids(ids)
    assert "2 to 15" in str(exc_info.value.detail)


def test_parse_model_ids_rejects_one():
    with pytest.raises(Exception) as exc_info:
        _parse_model_ids("1")
    assert "2 to 15" in str(exc_info.value.detail)


# ---------- _compute_estimated_cost unit tests (Task 2.2) ----------

from app.api.question_browser import _compute_estimated_cost


class _Preset:
    def __init__(self, provider_value: str, model_id: str, price_input=None, price_output=None):
        class _Provider:
            value = provider_value
        self.provider = _Provider()
        self.model_id = model_id
        self.price_input = price_input
        self.price_output = price_output


class _Generation:
    def __init__(self, tokens=None, input_tokens=None, output_tokens=None, cached_input_tokens=None):
        self.tokens = tokens
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cached_input_tokens = cached_input_tokens


def test_compute_estimated_cost_uses_preset_override_when_both_set():
    preset = _Preset("openai", "gpt-4.1", price_input=1.0, price_output=2.0)
    gen = _Generation(tokens=None, input_tokens=1000, output_tokens=500)
    cost = _compute_estimated_cost(gen, preset)
    # (1000 * 1.0 + 500 * 2.0) / 1_000_000 = 0.002
    assert cost is not None
    assert abs(cost - 0.002) < 1e-9


def test_compute_estimated_cost_ignores_partial_override():
    """Only one price override → fall through to catalog."""
    preset = _Preset("lmstudio", "local-model", price_input=1.0, price_output=None)
    gen = _Generation(tokens=100)
    cost = _compute_estimated_cost(gen, preset)
    assert cost == 0.0  # lmstudio is in DEFAULT_PRICE_PROVIDERS → free


def test_compute_estimated_cost_no_tokens_returns_none():
    preset = _Preset("openai", "gpt-4.1", price_input=1.0, price_output=2.0)
    gen = _Generation(tokens=None, input_tokens=None, output_tokens=None)
    assert _compute_estimated_cost(gen, preset) is None


def test_compute_estimated_cost_hosted_missing_catalog_returns_none():
    preset = _Preset("anthropic", "totally-fake-model-xyz")
    gen = _Generation(tokens=1000)
    assert _compute_estimated_cost(gen, preset) is None


def test_compute_estimated_cost_free_local_provider_returns_zero():
    preset = _Preset("lmstudio", "some-local-model-without-catalog")
    gen = _Generation(tokens=1000)
    assert _compute_estimated_cost(gen, preset) == 0.0


def test_compute_estimated_cost_preserves_sub_penny_precision():
    preset = _Preset("openai", "gpt-4.1", price_input=0.01, price_output=0.02)
    # (100 * 0.01 + 50 * 0.02) / 1_000_000 = 2e-6
    gen = _Generation(tokens=None, input_tokens=100, output_tokens=50)
    cost = _compute_estimated_cost(gen, preset)
    assert cost is not None
    assert cost > 0
    assert cost < 1e-4  # confirms sub-$0.0001 preserved (not rounded to 0)
