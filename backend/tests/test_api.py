# backend/tests/test_api.py
import os
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.db.database import get_db
from app.db.models import ModelPreset, ProviderType, RunStatus, SuiteGenerationJob
from app.schemas.models import DiscoveredModel, ModelValidationResult
from app.core.model_validation import validate_run_local_presets as real_validate_run_local_presets


class TestHealth:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestModels:
    def test_list_models_empty(self, client):
        response = client.get("/api/models/")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_model(self, client):
        model_data = {
            "name": "Test LM Studio Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/model-1"
        }
        response = client.post("/api/models/", json=model_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == model_data["name"]
        assert data["provider"] == model_data["provider"]
        assert data["has_api_key"] == False
        assert "id" in data

    def test_create_model_uses_catalog_pricing_provenance_by_default(self, client):
        response = client.post("/api/models/", json={
            "name": "Catalog GPT",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4.1",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 2.0
        assert data["price_output"] == 8.0
        assert data["price_source"] == "catalog"
        assert data["price_currency"] == "USD"

    def test_create_model_marks_explicit_price_override_as_manual(self, client):
        response = client.post("/api/models/", json={
            "name": "Manual GPT",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4.1",
            "price_input": 9.0,
            "price_output": 18.0,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["price_source"] == "manual"
        assert data["price_source_url"] is None

    def test_update_model_clears_stale_catalog_pricing_when_new_model_has_no_match(self, client):
        create_resp = client.post("/api/models/", json={
            "name": "Catalog GPT",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4.1",
        })
        model_id = create_resp.json()["id"]

        update_resp = client.put(f"/api/models/{model_id}", json={
            "model_id": "unknown-model-without-catalog-price",
        })
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["price_input"] is None
        assert data["price_output"] is None
        assert data["price_source"] is None
        assert data["price_source_url"] is None
        assert data["price_checked_at"] is None
        assert data["price_currency"] is None

    def test_create_model_with_api_key(self, client):
        model_data = {
            "name": "Test OpenAI Model",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4",
            "api_key": "sk-test123"
        }
        response = client.post("/api/models/", json=model_data)
        assert response.status_code == 200
        data = response.json()
        assert data["has_api_key"] == True

    def test_get_model(self, client):
        # Create a model first
        model_data = {
            "name": "Get Test Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/model"
        }
        create_response = client.post("/api/models/", json=model_data)
        model_id = create_response.json()["id"]

        # Get the model
        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        assert response.json()["name"] == model_data["name"]

    def test_get_model_not_found(self, client):
        response = client.get("/api/models/9999")
        assert response.status_code == 404

    def test_delete_model(self, client):
        # Create a model first
        model_data = {
            "name": "Delete Test Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/model"
        }
        create_response = client.post("/api/models/", json=model_data)
        model_id = create_response.json()["id"]

        # Archive the model (soft delete)
        response = client.delete(f"/api/models/{model_id}")
        assert response.status_code == 200

        # Model still exists via direct GET
        get_response = client.get(f"/api/models/{model_id}")
        assert get_response.status_code == 200

        # But hidden from default list
        list_response = client.get("/api/models/")
        listed_ids = [m["id"] for m in list_response.json()]
        assert model_id not in listed_ids

        # Visible when requesting archived
        list_all = client.get("/api/models/?include_archived=true")
        all_ids = [m["id"] for m in list_all.json()]
        assert model_id in all_ids

    def test_create_model_with_reasoning(self, client):
        """API should accept and return reasoning fields."""
        response = client.post("/api/models/", json={
            "name": "GPT-5.2 High Reasoning",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-5.2",
            "is_reasoning": True,
            "reasoning_level": "high"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["is_reasoning"] is True
        assert data["reasoning_level"] == "high"

    def test_update_model_reasoning(self, client):
        """API should allow updating reasoning fields."""
        # First create
        create_resp = client.post("/api/models/", json={
            "name": "Test Model",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-5.2"
        })
        model_id = create_resp.json()["id"]

        # Then update
        update_resp = client.put(f"/api/models/{model_id}", json={
            "is_reasoning": True,
            "reasoning_level": "xhigh"
        })
        assert update_resp.status_code == 200
        assert update_resp.json()["is_reasoning"] is True
        assert update_resp.json()["reasoning_level"] == "xhigh"

    def test_create_model_rejects_custom_temperature_above_range(self, client):
        response = client.post("/api/models/", json={
            "name": "Too Hot",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4.1",
            "custom_temperature": 2.5,
        })
        assert response.status_code == 422

    def test_update_model_rejects_custom_temperature_above_range(self, client):
        create_resp = client.post("/api/models/", json={
            "name": "Update Test",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-4.1",
        })
        model_id = create_resp.json()["id"]

        update_resp = client.put(f"/api/models/{model_id}", json={
            "custom_temperature": 2.5,
        })
        assert update_resp.status_code == 422

    def test_create_deepseek_reasoner_forces_reasoning(self, client):
        response = client.post("/api/models/", json={
            "name": "DeepSeek Reasoner",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1/chat/completions",
            "model_id": "deepseek-reasoner",
            "is_reasoning": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["is_reasoning"] is True
        assert data["reasoning_level"] is None

    def test_update_deepseek_reasoner_forces_reasoning(self, client):
        create_resp = client.post("/api/models/", json={
            "name": "DeepSeek Chat",
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com/v1/chat/completions",
            "model_id": "deepseek-chat",
        })
        model_id = create_resp.json()["id"]

        update_resp = client.put(f"/api/models/{model_id}", json={
            "model_id": "deepseek-reasoner",
            "is_reasoning": False,
        })
        assert update_resp.status_code == 200
        data = update_resp.json()
        assert data["is_reasoning"] is True
        assert data["reasoning_level"] is None

    def test_model_response_includes_pricing_provenance(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Priced GPT",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-4.1",
                price_input=2.0,
                price_output=8.0,
                price_source="catalog",
                price_source_url="https://openai.com/api/pricing/",
                price_checked_at=datetime(2026, 3, 26, tzinfo=timezone.utc),
                price_currency="USD",
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_source"] == "catalog"
        assert "price_source_url" in data
        assert data["price_currency"] == "USD"
        assert data["price_checked_at"] == "2026-03-26T00:00:00"

    def test_get_model_allows_legacy_custom_temperature_values(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Legacy Temp",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-4.1",
                custom_temperature=2.5,
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        assert response.json()["custom_temperature"] == 2.5

    def test_get_model_backfills_missing_catalog_pricing_for_legacy_preset(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Legacy Catalog GPT",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-4.1",
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 2.0
        assert data["price_output"] == 8.0
        assert data["price_source"] == "catalog"
        assert data["price_source_url"] == "https://developers.openai.com/api/docs/models/gpt-4.1"
        assert data["price_currency"] == "USD"
        assert data["price_checked_at"] == "2026-03-26T00:00:00"

        verify_gen = app.dependency_overrides[get_db]()
        verify_db = next(verify_gen)
        try:
            persisted = verify_db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
            assert persisted.price_input == 2.0
            assert persisted.price_output == 8.0
            assert persisted.price_source == "catalog"
            assert persisted.price_source_url == "https://developers.openai.com/api/docs/models/gpt-4.1"
            assert persisted.price_currency == "USD"
            assert persisted.price_checked_at == datetime(2026, 3, 26)
        finally:
            try:
                next(verify_gen)
            except StopIteration:
                pass

    def test_list_models_backfills_missing_catalog_pricing_for_legacy_preset(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Legacy Sonnet",
                provider=ProviderType.anthropic,
                base_url="https://api.anthropic.com/v1/messages",
                model_id="claude-sonnet-4-5-20250929",
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get("/api/models/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        legacy = data[0]
        assert legacy["id"] == model_id
        assert legacy["price_input"] == 3.0
        assert legacy["price_output"] == 15.0
        assert legacy["price_source"] == "catalog"
        assert legacy["price_source_url"] == "https://docs.anthropic.com/en/docs/about-claude/pricing"
        assert legacy["price_currency"] == "USD"

        verify_gen = app.dependency_overrides[get_db]()
        verify_db = next(verify_gen)
        try:
            persisted = verify_db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
            assert persisted.price_input == 3.0
            assert persisted.price_output == 15.0
            assert persisted.price_source == "catalog"
            assert persisted.price_source_url == "https://docs.anthropic.com/en/docs/about-claude/pricing"
            assert persisted.price_currency == "USD"
        finally:
            try:
                next(verify_gen)
            except StopIteration:
                pass

    def test_get_model_repairs_partial_legacy_catalog_pricing(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Partially Priced GPT",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-4.1",
                price_input=99.0,
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 2.0
        assert data["price_output"] == 8.0
        assert data["price_source"] == "catalog"

    def test_get_model_refreshes_stale_persisted_catalog_pricing(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Stale GPT Catalog Row",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-5.3-chat-latest",
                price_input=1.25,
                price_output=10.0,
                price_source="catalog",
                price_source_url="https://openai.com/api/pricing/",
                price_checked_at=datetime(2026, 3, 26),
                price_currency="USD",
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 1.75
        assert data["price_output"] == 14.0
        assert data["price_source"] == "catalog"
        assert data["price_source_url"] == "https://developers.openai.com/api/docs/models/gpt-5.3-chat-latest"
        assert data["price_checked_at"] == "2026-04-20T00:00:00"

    def test_get_model_backfills_openrouter_price_provenance_for_legacy_rows(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Legacy OpenRouter Row",
                provider=ProviderType.openrouter,
                base_url="https://openrouter.ai/api/v1/chat/completions",
                model_id="minimax/minimax-m2.7",
                price_input=0.3,
                price_output=1.2,
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 0.3
        assert data["price_output"] == 1.2
        assert data["price_source"] == "openrouter_api"
        assert data["price_source_url"] == "https://openrouter.ai/api/v1/models"
        assert data["price_currency"] == "USD"
        assert data["price_checked_at"] is None

    def test_get_model_does_not_overwrite_manual_pricing_on_read(self, client):
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            preset = ModelPreset(
                name="Manual GPT",
                provider=ProviderType.openai,
                base_url="https://api.openai.com/v1/chat/completions",
                model_id="gpt-4.1",
                price_input=9.0,
                price_output=18.0,
                price_source="manual",
                price_currency="USD",
            )
            db.add(preset)
            db.commit()
            db.refresh(preset)
            model_id = preset.id
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass

        response = client.get(f"/api/models/{model_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["price_input"] == 9.0
        assert data["price_output"] == 18.0
        assert data["price_source"] == "manual"
        assert data["price_source_url"] is None

    def test_model_test_endpoint_returns_richer_exact_check_data(self, client):
        create_response = client.post("/api/models/", json={
            "name": "Local GPT-OSS",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "openai/gpt-oss-120b",
        })
        model_id = create_response.json()["id"]

        with patch("app.api.models.test_connection", new=AsyncMock(return_value={
            "ok": True,
            "reachable": True,
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "openai/gpt-oss-120b",
            "resolved_model_id": "openai/gpt-oss-120b",
            "model_info": {"arch": "gpt-oss", "quant": "MXFP4", "format": "gguf"},
            "reasoning_supported_levels": ["low", "medium", "high", "xhigh"],
            "validation_status": "available_exact",
            "metadata_drift": [],
        })):
            response = client.post(f"/api/models/{model_id}/test")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["reachable"] is True
        assert data["resolved_model_id"] == "openai/gpt-oss-120b"
        assert data["model_info"]["arch"] == "gpt-oss"
        assert data["reasoning_supported_levels"] == ["low", "medium", "high", "xhigh"]
        assert data["validation_status"] == "available_exact"
        assert data["metadata_drift"] == []

    def test_validate_models_returns_local_validation_results(self, client):
        validation_results = [
            {
                "preset_id": 1,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "available_exact",
                "message": "Exact local model match is available.",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": None,
            },
            {
                "preset_id": 2,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "available_metadata_drift",
                "message": "Model is available but metadata drift was detected.",
                "live_match": None,
                "metadata_drift": ["selected_variant"],
                "suggested_action": "Review metadata drift",
            },
            {
                "preset_id": 3,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "available_retarget_suggestion",
                "message": "A likely renamed local model was found.",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": "Retarget to openai/gpt-oss-120b@mxfp4",
            },
            {
                "preset_id": 4,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "missing",
                "message": "No matching local model was found.",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": "Archive missing local preset",
            },
            {
                "preset_id": 5,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "server_unreachable",
                "message": "Local server is unreachable.",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": "Check that the local server is running.",
            },
            {
                "preset_id": 6,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "needs_probe",
                "message": "Multiple plausible live matches were found.",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": "Use Test to confirm the exact preset.",
            },
            {
                "preset_id": 7,
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "status": "validation_failed",
                "message": "Validation failed: malformed discovery payload",
                "live_match": None,
                "metadata_drift": [],
                "suggested_action": None,
            },
        ]

        with patch("app.api.models.validate_local_presets", new=AsyncMock(return_value=validation_results)):
            response = client.post("/api/models/validate", json={"scope": "local"})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert {item["status"] for item in data} == {
            "available_exact",
            "available_metadata_drift",
            "available_retarget_suggestion",
            "missing",
            "server_unreachable",
            "needs_probe",
            "validation_failed",
        }


class TestBenchmarks:
    def _create_test_models(self, client):
        """Helper to create test models for benchmark tests."""
        models = []
        for i in range(2):
            response = client.post("/api/models/", json={
                "name": f"Test Model {i}",
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "model_id": f"test/model-{i}"
            })
            models.append(response.json()["id"])
        return models

    def _create_test_judge(self, client):
        """Helper to create a separate judge model (avoids self-judging)."""
        response = client.post("/api/models/", json={
            "name": "Test Judge",
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1/messages",
            "model_id": "claude-sonnet-4-5-20250929"
        })
        return response.json()["id"]

    def test_list_benchmarks_empty(self, client):
        response = client.get("/api/benchmarks/")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_benchmark(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        benchmark_data = {
            "name": "Test Benchmark",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [
                {"name": "Quality", "description": "Overall quality", "weight": 1.0}
            ],
            "questions": [
                {"system_prompt": "You are helpful", "user_prompt": "Say hello"}
            ]
        }

        response = client.post("/api/benchmarks/", json=benchmark_data)
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] == "started"

    def test_create_benchmark_invalid_model(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        benchmark_data = {
            "name": "Test Benchmark",
            "model_ids": [9999],  # Invalid model ID
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [{"system_prompt": "You are helpful", "user_prompt": "Say hello"}]
        }

        response = client.post("/api/benchmarks/", json=benchmark_data)
        assert response.status_code == 400

    def test_create_benchmark_blocks_missing_local_model(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        missing_result = ModelValidationResult(
            preset_id=model_ids[0],
            provider="lmstudio",
            base_url="http://localhost:1234/v1/chat/completions",
            status="missing",
            message="No matching local model was found.",
            metadata_drift=[],
            suggested_action="Archive missing local preset",
        )

        with patch("app.api.benchmarks.validate_run_local_presets", new=AsyncMock(return_value=[missing_result])):
            response = client.post("/api/benchmarks/", json={
                "name": "Missing local preset",
                "model_ids": model_ids,
                "judge_ids": [judge_id],
                "judge_mode": "comparison",
                "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
                "questions": [{"system_prompt": "You are helpful", "user_prompt": "Say hello"}],
            })

        assert response.status_code == 400
        assert "missing" in response.json()["detail"].lower()

    def test_create_benchmark_blocks_unreachable_local_server(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        unreachable_result = ModelValidationResult(
            preset_id=model_ids[0],
            provider="lmstudio",
            base_url="http://localhost:1234/v1/chat/completions",
            status="server_unreachable",
            message="Local server is unreachable.",
            metadata_drift=[],
            suggested_action="Check that the local server is running.",
        )

        with patch("app.api.benchmarks.validate_run_local_presets", new=AsyncMock(return_value=[unreachable_result])):
            response = client.post("/api/benchmarks/", json={
                "name": "Unreachable local server",
                "model_ids": model_ids,
                "judge_ids": [judge_id],
                "judge_mode": "comparison",
                "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
                "questions": [{"system_prompt": "You are helpful", "user_prompt": "Say hello"}],
            })

        assert response.status_code == 400
        assert "server_unreachable" in response.json()["detail"].lower()

    def test_create_benchmark_blocks_needs_probe_local_model(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        probe_result = ModelValidationResult(
            preset_id=model_ids[0],
            provider="lmstudio",
            base_url="http://localhost:1234/v1/chat/completions",
            status="needs_probe",
            message="Multiple plausible live matches were found.",
            metadata_drift=[],
            suggested_action="Use Test to confirm the exact preset.",
        )

        with patch("app.api.benchmarks.validate_run_local_presets", new=AsyncMock(return_value=[probe_result])):
            response = client.post("/api/benchmarks/", json={
                "name": "Needs probe",
                "model_ids": model_ids,
                "judge_ids": [judge_id],
                "judge_mode": "comparison",
                "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
                "questions": [{"system_prompt": "You are helpful", "user_prompt": "Say hello"}],
            })

        assert response.status_code == 400
        assert "needs_probe" in response.json()["detail"].lower()

    def test_create_benchmark_allows_metadata_drift_and_syncs_safe_fields(self, client):
        model_response = client.post("/api/models/", json={
            "name": "Drifted LM Studio Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "openai/gpt-oss-120b",
            "context_limit": 4096,
            "quantization": "Q4_K_M",
            "quantization_bits": 4.0,
            "selected_variant": "openai/gpt-oss-120b@q4_k_m",
            "model_format": "gguf",
            "parameter_count": "120B",
        })
        model_id = model_response.json()["id"]

        judge_id = self._create_test_judge(client)

        live_match = DiscoveredModel(
            model_id="openai/gpt-oss-120b",
            name="Drifted LM Studio Model",
            is_reasoning=True,
            reasoning_level="high",
            supports_vision=False,
            context_limit=8192,
            quantization="MXFP4",
            quantization_bits=8.0,
            selected_variant="openai/gpt-oss-120b@mxfp4",
            model_architecture="gpt-oss",
            parameter_count="120B",
            model_format="gguf",
        )

        with patch("app.api.benchmarks.validate_run_local_presets", new=real_validate_run_local_presets), \
             patch("app.core.model_validation._discover_local_inventory", new=AsyncMock(return_value=[live_match])):
            response = client.post("/api/benchmarks/", json={
                "name": "Metadata drift benchmark",
                "model_ids": [model_id],
                "judge_ids": [judge_id],
                "judge_mode": "comparison",
                "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
                "questions": [{"system_prompt": "You are helpful", "user_prompt": "Say hello"}],
            })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started"

        db = next(app.dependency_overrides[get_db]())
        try:
            preset = db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
            assert preset.context_limit == 8192
            assert preset.quantization_bits == 8.0
            assert preset.selected_variant == "openai/gpt-oss-120b@mxfp4"
            assert preset.quantization == "Q4_K_M"
        finally:
            db.close()

    def test_get_benchmark(self, client):
        model_ids = self._create_test_models(client)
        judge_id = self._create_test_judge(client)

        # Create benchmark
        create_response = client.post("/api/benchmarks/", json={
            "name": "Get Test Benchmark",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "separate",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [{"system_prompt": "Test", "user_prompt": "Test question"}]
        })
        benchmark_id = create_response.json()["id"]

        # Get benchmark
        response = client.get(f"/api/benchmarks/{benchmark_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Get Test Benchmark"
        assert data["judge_mode"] == "separate"
        assert data["preset_labels"][str(model_ids[0])] == "Test Model 0"
        assert data["preset_labels"][str(judge_id)] == "Test Judge"
        assert len(data["questions"]) == 1


class TestQuestions:
    def test_generate_questions_without_model(self, client):
        response = client.post("/api/questions/generate", json={
            "model_id": 9999,
            "topic": "Test topic",
            "count": 3
        })
        assert response.status_code == 404


class TestExports:
    def _create_benchmark_with_data(self, client):
        """Helper to create a benchmark for export tests."""
        # Create models
        model_ids = []
        for i in range(2):
            response = client.post("/api/models/", json={
                "name": f"Export Model {i}",
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "model_id": f"test/export-{i}"
            })
            model_ids.append(response.json()["id"])

        # Create separate judge
        judge_resp = client.post("/api/models/", json={
            "name": "Export Judge",
            "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1/messages",
            "model_id": "claude-sonnet-4-5-20250929"
        })
        judge_id = judge_resp.json()["id"]

        # Create benchmark
        response = client.post("/api/benchmarks/", json={
            "name": "Export Test",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{"system_prompt": "Test", "user_prompt": "Export test"}]
        })
        return response.json()["id"]

    def test_export_json(self, client):
        benchmark_id = self._create_benchmark_with_data(client)
        response = client.get(f"/api/benchmarks/{benchmark_id}/export/json")
        assert response.status_code == 200
        data = response.json()
        assert data["run"]["name"] == "Export Test"
        assert "questions" in data

    def test_export_csv(self, client):
        benchmark_id = self._create_benchmark_with_data(client)
        response = client.get(f"/api/benchmarks/{benchmark_id}/export/csv")
        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_export_html(self, client):
        benchmark_id = self._create_benchmark_with_data(client)
        response = client.get(f"/api/benchmarks/{benchmark_id}/export/html")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "BeLLMark" in response.text

    def test_export_json_includes_judge_agreement_summary(self, client):
        run_id = self._create_benchmark_with_data(client)
        export = client.get(f"/api/benchmarks/{run_id}/export/json").json()
        assert "judge_summary" in export

    def test_compare_runs(self, client):
        id1 = self._create_benchmark_with_data(client)
        id2 = self._create_benchmark_with_data(client)

        response = client.get(f"/api/benchmarks/compare?ids={id1},{id2}")
        assert response.status_code == 200
        data = response.json()
        assert "runs" in data
        assert len(data["runs"]) == 2

    def test_compare_route_is_reachable(self, client):
        """Test that /compare route is not shadowed by /{run_id} route."""
        response = client.get("/api/benchmarks/compare?ids=999")
        assert response.status_code != 422, "Route /{run_id} is shadowing /compare"


class TestRunConfigSnapshot:
    def test_run_config_snapshot_does_not_change_when_preset_changes(self, client):
        # create two models and a separate judge
        tb = TestBenchmarks()
        model_ids = tb._create_test_models(client)
        judge_id = tb._create_test_judge(client)
        benchmark_data = {
            "name": "Snapshot Test",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [{"system_prompt": "sys", "user_prompt": "user"}],
        }
        res = client.post("/api/benchmarks/", json=benchmark_data)
        run_id = res.json()["id"]

        # update model preset name after run created
        db = next(app.dependency_overrides[get_db]())
        from app.db.models import ModelPreset
        m = db.query(ModelPreset).filter(ModelPreset.id == model_ids[0]).first()
        original_name = m.name
        m.name = "CHANGED NAME"
        db.commit()

        # fetch run export JSON and verify it still contains original snapshot name
        export = client.get(f"/api/benchmarks/{run_id}/export/json").json()
        assert "run_config_snapshot" in export["run"]
        assert export["run"]["run_config_snapshot"]["models"][0]["name"] == original_name
        assert export["run"]["run_config_snapshot"]["models"][0]["name"] != "CHANGED NAME"


class TestLatencyMetrics:
    def test_generation_has_latency_field(self):
        """Verify that Generation model has latency_ms field."""
        from app.db.models import Generation
        assert hasattr(Generation, 'latency_ms')

    def test_judgment_has_latency_field(self):
        """Verify that Judgment model has latency_ms field."""
        from app.db.models import Judgment
        assert hasattr(Judgment, 'latency_ms')


class TestSuites:
    def test_pipelines_endpoint_returns_empty_list_when_idle(self, client):
        resp = client.get("/api/suites/pipelines")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_suite(self, client):
        data = {
            "name": "Test Suite",
            "description": "A test suite",
            "items": [
                {"system_prompt": "sys1", "user_prompt": "user1"},
                {"system_prompt": "sys2", "user_prompt": "user2"}
            ]
        }
        res = client.post("/api/suites/", json=data)
        assert res.status_code == 200
        assert res.json()["name"] == "Test Suite"
        assert len(res.json()["items"]) == 2

    def test_list_suites(self, client):
        res = client.get("/api/suites/")
        assert res.status_code == 200

    def test_get_suite(self, client):
        # Create then get
        data = {"name": "Get Test", "description": "", "items": [{"system_prompt": "s", "user_prompt": "u"}]}
        create_res = client.post("/api/suites/", json=data)
        suite_id = create_res.json()["id"]

        res = client.get(f"/api/suites/{suite_id}")
        assert res.status_code == 200
        assert res.json()["name"] == "Get Test"

    def test_delete_suite(self, client):
        # Create then delete
        data = {"name": "Delete Test", "description": "", "items": [{"system_prompt": "s", "user_prompt": "u"}]}
        create_res = client.post("/api/suites/", json=data)
        suite_id = create_res.json()["id"]

        # Delete
        res = client.delete(f"/api/suites/{suite_id}")
        assert res.status_code == 200

        # Verify deleted
        res = client.get(f"/api/suites/{suite_id}")
        assert res.status_code == 404

    def test_delete_generated_suite_clears_generation_job_refs(self, client):
        data = {"name": "Generated Delete Test", "description": "", "items": [{"system_prompt": "s", "user_prompt": "u"}]}
        create_res = client.post("/api/suites/", json=data)
        suite_id = create_res.json()["id"]

        db = next(client.app.dependency_overrides[get_db]())
        try:
            job = SuiteGenerationJob(
                session_id="delete-suite-job-ref",
                status=RunStatus.completed,
                name="Generated Delete Test",
                topic="Delete test",
                count=1,
                generator_model_ids=[1],
                editor_model_id=1,
                reviewer_model_ids=[],
                pipeline_config={
                    "difficulty": "balanced",
                    "categories": [],
                    "generate_answers": True,
                    "criteria_depth": "basic",
                    "generation_concurrency": 5,
                    "review_batch_concurrency": 5,
                },
                coverage_mode="none",
                coverage_spec=None,
                max_topics_per_question=1,
                context_attachment_id=None,
                phase="save",
                snapshot_payload={},
                checkpoint_payload={},
                suite_id=suite_id,
            )
            db.add(job)
            db.commit()
        finally:
            db.close()

        res = client.delete(f"/api/suites/{suite_id}")
        assert res.status_code == 200

        db = next(client.app.dependency_overrides[get_db]())
        try:
            refreshed = (
                db.query(SuiteGenerationJob)
                .filter(SuiteGenerationJob.session_id == "delete-suite-job-ref")
                .first()
            )
            assert refreshed is not None
            assert refreshed.suite_id is None
            assert refreshed.partial_suite_id is None
        finally:
            db.close()

    def test_update_suite(self, client):
        # Create suite
        data = {
            "name": "Original Name",
            "description": "Original desc",
            "items": [{"system_prompt": "sys1", "user_prompt": "user1"}]
        }
        create_res = client.post("/api/suites/", json=data)
        suite_id = create_res.json()["id"]

        # Update it
        update_data = {
            "name": "Updated Name",
            "description": "Updated desc",
            "items": [
                {"system_prompt": "new_sys1", "user_prompt": "new_user1"},
                {"system_prompt": "new_sys2", "user_prompt": "new_user2"}
            ]
        }
        res = client.put(f"/api/suites/{suite_id}", json=update_data)
        assert res.status_code == 200
        assert res.json()["name"] == "Updated Name"
        assert len(res.json()["items"]) == 2
        assert res.json()["items"][0]["system_prompt"] == "new_sys1"

    def test_update_suite_not_found(self, client):
        update_data = {"name": "X", "description": "", "items": [{"system_prompt": "s", "user_prompt": "u"}]}
        res = client.put("/api/suites/9999", json=update_data)
        assert res.status_code == 404

    def test_generate_suite_no_model(self, client):
        """Test that generation fails gracefully with invalid model."""
        res = client.post("/api/suites/generate", json={
            "name": "Generated Suite",
            "model_id": 9999,
            "topic": "Python best practices",
            "count": 3
        })
        assert res.status_code == 404

    def test_create_suite_from_run(self, client):
        # Create models, judge, and benchmark first
        tb = TestBenchmarks()
        model_ids = tb._create_test_models(client)
        judge_id = tb._create_test_judge(client)
        benchmark_data = {
            "name": "Source Run",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [
                {"system_prompt": "sys1", "user_prompt": "user1"},
                {"system_prompt": "sys2", "user_prompt": "user2"}
            ]
        }
        run_res = client.post("/api/benchmarks/", json=benchmark_data)
        run_id = run_res.json()["id"]

        # Create suite from run
        res = client.post(f"/api/suites/from-run/{run_id}", json={"name": "Suite from Run"})
        assert res.status_code == 200
        suite = res.json()
        assert suite["name"] == "Suite from Run"
        assert len(suite["items"]) == 2
        assert suite["items"][0]["system_prompt"] == "sys1"

    def test_create_suite_from_run_not_found(self, client):
        res = client.post("/api/suites/from-run/9999", json={"name": "Test"})
        assert res.status_code == 404

    def test_generate_suite_v2_returns_session_id(self, client):
        # Create a model preset first
        model_data = {
            "name": "Generator Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-model",
        }
        model_res = client.post("/api/models/", json=model_data)
        assert model_res.status_code == 200
        model_id = model_res.json()["id"]

        res = client.post("/api/suites/generate-v2", json={
            "name": "V2 Suite",
            "topic": "Python testing",
            "count": 5,
            "generator_model_id": model_id,
        })
        assert res.status_code == 200
        data = res.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0

    def test_generate_suite_v2_defaults_editor_to_generator_when_absent(self, client, monkeypatch):
        # The endpoint early-returns when BELLMARK_DISABLE_BACKGROUND_RUNS is set
        # (production safety: prevents background tasks from leaking into the prod
        # SessionLocal during tests). For this test we WANT the SuitePipeline path
        # to run so we can verify the kwargs the API constructs — we replace the
        # pipeline + create_task with patches that intercept without spawning work.
        monkeypatch.delenv("BELLMARK_DISABLE_BACKGROUND_RUNS", raising=False)

        generator = client.post("/api/models/", json={
            "name": "Generator Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-model",
        }).json()["id"]

        captured = {}

        def fake_suite_pipeline(*args, **kwargs):
            captured["kwargs"] = kwargs
            pipeline = MagicMock()
            pipeline.run = AsyncMock()
            return pipeline

        def fake_create_task(coro):
            coro.close()
            return MagicMock()

        with (
            patch("app.core.suite_pipeline.SuitePipeline", side_effect=fake_suite_pipeline),
            patch("app.api.suites.asyncio.create_task", side_effect=fake_create_task),
        ):
            res = client.post("/api/suites/generate-v2", json={
                "name": "V2 Suite",
                "topic": "Python testing",
                "count": 5,
                "generator_model_id": generator,
            })

        assert res.status_code == 200
        kwargs = captured["kwargs"]
        assert kwargs["generator_presets"][0].id == generator
        assert kwargs["editor_preset"].id == generator

    def test_generate_suite_v2_accepts_generator_pool_and_explicit_editor(self, client, monkeypatch):
        # See sibling test: must unset BELLMARK_DISABLE_BACKGROUND_RUNS so the
        # endpoint reaches the SuitePipeline construction path that we patch.
        monkeypatch.delenv("BELLMARK_DISABLE_BACKGROUND_RUNS", raising=False)

        generator_a = client.post("/api/models/", json={
            "name": "Generator A",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-a",
        }).json()["id"]
        generator_b = client.post("/api/models/", json={
            "name": "Generator B",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-b",
        }).json()["id"]
        editor = client.post("/api/models/", json={
            "name": "Editor",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/editor",
        }).json()["id"]

        captured = {}

        def fake_suite_pipeline(*args, **kwargs):
            captured["kwargs"] = kwargs
            pipeline = MagicMock()
            pipeline.run = AsyncMock()
            return pipeline

        def fake_create_task(coro):
            coro.close()
            return MagicMock()

        with (
            patch("app.core.suite_pipeline.SuitePipeline", side_effect=fake_suite_pipeline),
            patch("app.api.suites.asyncio.create_task", side_effect=fake_create_task),
        ):
            res = client.post("/api/suites/generate-v2", json={
                "name": "V2 Suite",
                "topic": "Python testing",
                "count": 5,
                "generator_model_ids": [generator_a, generator_b],
                "editor_model_id": editor,
            })

        assert res.status_code == 200
        kwargs = captured["kwargs"]
        assert [preset.id for preset in kwargs["generator_presets"]] == [generator_a, generator_b]
        assert kwargs["editor_preset"].id == editor

    def test_generate_suite_v2_rejects_duplicate_generator_ids(self, client):
        generator = client.post("/api/models/", json={
            "name": "Generator Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-model",
        }).json()["id"]
        editor = client.post("/api/models/", json={
            "name": "Editor Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/editor-model",
        }).json()["id"]

        res = client.post("/api/suites/generate-v2", json={
            "name": "V2 Suite",
            "topic": "Python testing",
            "count": 5,
            "generator_model_id": generator,
            "generator_model_ids": [generator, generator],
            "editor_model_id": editor,
        })

        assert res.status_code == 422

    def test_generate_suite_v2_rejects_more_than_three_reviewers(self, client):
        res = client.post("/api/suites/generate-v2", json={
            "name": "V2 Suite",
            "topic": "Testing",
            "count": 5,
            "generator_model_id": 1,
            "reviewer_model_ids": [1, 2, 3, 4],  # 4 reviewers → 422
        })
        assert res.status_code == 422

    def test_generate_suite_v2_rejects_non_text_context_attachment(self, client):
        """POST with an image attachment ID should return 422."""
        from app.main import app
        from app.db.database import get_db
        from app.db.models import Attachment

        # Insert an image attachment directly into the test DB
        db_gen = app.dependency_overrides[get_db]()
        db = next(db_gen)
        try:
            img_attachment = Attachment(
                filename="photo.png",
                storage_path="uploads/photo.png",
                mime_type="image/png",
                size_bytes=1024,
            )
            db.add(img_attachment)
            db.commit()
            db.refresh(img_attachment)
            attachment_id = img_attachment.id
        finally:
            db.close()

        # Create a generator model
        model_res = client.post("/api/models/", json={
            "name": "Gen Model",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen-model",
        })
        model_id = model_res.json()["id"]

        res = client.post("/api/suites/generate-v2", json={
            "name": "V2 Suite",
            "topic": "Testing",
            "count": 5,
            "generator_model_id": model_id,
            "context_attachment_id": attachment_id,
        })
        assert res.status_code == 422

    def test_parse_coverage_outline_endpoint_returns_normalized_spec(self, client):
        res = client.post("/api/suites/parse-coverage-outline", json={
            "outline": "A. LLM\n- Topic One\n- Topic Two",
        })

        assert res.status_code == 200
        body = res.json()
        assert body["spec"]["groups"][0]["id"] == "a"
        assert len(body["spec"]["groups"][0]["leaves"]) == 2

    def test_generate_suite_v2_rejects_strict_coverage_when_count_below_leaf_count(self, client):
        generator = client.post("/api/models/", json={
            "name": "Generator",
            "provider": "lmstudio",
            "base_url": "http://localhost:1234/v1/chat/completions",
            "model_id": "test/gen",
        }).json()["id"]

        res = client.post("/api/suites/generate-v2", json={
            "name": "Coverage Suite",
            "topic": "AI engineering",
            "count": 1,
            "generator_model_id": generator,
            "coverage_mode": "strict_leaf_coverage",
            "coverage_spec": {
                "version": "1",
                "groups": [
                    {
                        "id": "a",
                        "label": "A",
                        "leaves": [
                            {"id": "a.one", "label": "One"},
                            {"id": "a.two", "label": "Two"},
                        ],
                    }
                ],
            },
        })

        assert res.status_code == 422

    def test_export_suite_includes_optional_coverage_metadata(self, client):
        create_resp = client.post("/api/suites/", json={
            "name": "Export Coverage Meta",
            "description": "",
            "items": [
                {
                    "system_prompt": "sys",
                    "user_prompt": "usr",
                }
            ],
        })
        suite_id = create_resp.json()["id"]

        exported = client.get(f"/api/suites/{suite_id}/export")

        assert exported.status_code == 200
        body = exported.json()
        assert "questions" in body
        assert "generation_metadata" in body
        assert "coverage_report" in body
        assert "dedupe_report" in body
        assert "coverage_topic_ids" in body["questions"][0]
        assert "coverage_topic_labels" in body["questions"][0]
        assert "generation_slot_index" in body["questions"][0]

    def test_pipelines_endpoint_returns_full_snapshot_during_active_run(self, client):
        import time

        from app.core.suite_pipeline import PipelineConfig, SuitePipeline, active_suite_pipelines

        mock_preset = MagicMock(spec=ModelPreset)
        mock_preset.name = "Test Gen"
        mock_preset.model_id = "test/gen"

        pipeline = SuitePipeline(
            session_id="reconnect-test",
            generator_preset=mock_preset,
            reviewer_presets=[],
            name="Reconnect Test",
            topic="Testing",
            count=10,
            config=PipelineConfig(),
            suite_manager=None,
        )
        pipeline._current_phase = "generate"
        pipeline._batch = 3
        pipeline._total_batches = 2
        pipeline._call_started_at = time.time() - 30
        pipeline._model = "Test Gen"
        pipeline._questions_generated = 5

        active_suite_pipelines["reconnect-test"] = pipeline
        try:
            resp = client.get("/api/suites/pipelines")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            snap = data[0]
            assert snap["session_id"] == "reconnect-test"
            assert snap["phase"] == "generate"
            assert snap["batch"] == 3
            assert snap["call_started_at"] is not None
            assert snap["model"] == "Test Gen"
            assert snap["questions_generated"] == 5
            assert snap["phases"] is not None
            assert "recent_log" in snap
        finally:
            active_suite_pipelines.pop("reconnect-test", None)


class TestSuiteTracking:
    def test_benchmark_tracks_source_suite(self, client):
        # Create suite first
        suite_data = {
            "name": "Source Suite",
            "description": "",
            "items": [{"system_prompt": "sys", "user_prompt": "user"}]
        }
        suite_res = client.post("/api/suites/", json=suite_data)
        suite_id = suite_res.json()["id"]

        # Create models and separate judge
        tb = TestBenchmarks()
        model_ids = tb._create_test_models(client)
        judge_id = tb._create_test_judge(client)

        # Create benchmark referencing suite
        benchmark_data = {
            "name": "Tracked Run",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{"system_prompt": "sys", "user_prompt": "user"}],
            "source_suite_id": suite_id
        }
        run_res = client.post("/api/benchmarks/", json=benchmark_data)
        run_id = run_res.json()["id"]

        # Verify suite is tracked
        detail_res = client.get(f"/api/benchmarks/{run_id}")
        assert detail_res.json().get("source_suite_id") == suite_id

    def test_benchmark_without_suite_tracking(self, client):
        tb = TestBenchmarks()
        model_ids = tb._create_test_models(client)
        judge_id = tb._create_test_judge(client)
        benchmark_data = {
            "name": "No Suite Run",
            "model_ids": model_ids,
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Test", "weight": 1.0}],
            "questions": [{"system_prompt": "sys", "user_prompt": "user"}]
        }
        run_res = client.post("/api/benchmarks/", json=benchmark_data)
        run_id = run_res.json()["id"]

        detail_res = client.get(f"/api/benchmarks/{run_id}")
        assert detail_res.json().get("source_suite_id") is None


class TestStartupValidation:
    def test_startup_warns_missing_secret_key(self):
        """Startup should warn if BELLMARK_SECRET_KEY is not set."""
        original = os.environ.get("BELLMARK_SECRET_KEY")
        try:
            os.environ.pop("BELLMARK_SECRET_KEY", None)
            from app.main import _validate_config
            warnings, fatal = _validate_config()
            assert any("BELLMARK_SECRET_KEY" in w for w in warnings)
            assert fatal is True
        finally:
            if original:
                os.environ["BELLMARK_SECRET_KEY"] = original

    def test_startup_no_warnings_with_valid_config(self):
        """No warnings when secret key is properly set."""
        original = os.environ.get("BELLMARK_SECRET_KEY")
        try:
            os.environ["BELLMARK_SECRET_KEY"] = "a-sufficiently-long-secret-key"
            from app.main import _validate_config
            warnings, fatal = _validate_config()
            assert len(warnings) == 0
            assert fatal is False
        finally:
            if original:
                os.environ["BELLMARK_SECRET_KEY"] = original
            else:
                os.environ.pop("BELLMARK_SECRET_KEY", None)

    def test_startup_detects_legacy_encrypted_keys(self, client):
        """Startup should warn when model presets use legacy encryption format."""
        import base64
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from app.main import _check_legacy_keys

        secret = "test-secret-key-for-legacy"
        original = os.environ.get("BELLMARK_SECRET_KEY")
        os.environ["BELLMARK_SECRET_KEY"] = secret

        try:
            # Create a model preset with legacy-format encrypted key
            # Legacy format: fixed salt "bellmark_salt_v1", plain Fernet token
            salt = b"bellmark_salt_v1"
            kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
            key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
            fernet = Fernet(key)
            legacy_encrypted = fernet.encrypt(b"sk-test-key-12345").decode()

            response = client.post("/api/models/", json={
                "name": "Legacy Model",
                "provider": "openai",
                "base_url": "https://api.openai.com/v1",
                "model_id": "gpt-4",
                "api_key": "sk-test-key-12345"
            })
            preset_id = response.json()["id"]

            # Directly set legacy encrypted value in DB
            db = next(app.dependency_overrides[get_db]())
            from app.db.models import ModelPreset
            preset = db.query(ModelPreset).filter(ModelPreset.id == preset_id).first()
            preset.api_key_encrypted = legacy_encrypted
            db.commit()

            warnings = _check_legacy_keys(db)
            assert any("legacy encryption" in w for w in warnings)
            assert any("Legacy Model" in w for w in warnings)
            db.close()
        finally:
            if original:
                os.environ["BELLMARK_SECRET_KEY"] = original
            else:
                os.environ.pop("BELLMARK_SECRET_KEY", None)


class TestCORS:
    def test_cors_rejects_unknown_origin(self, client):
        """CORS should not allow arbitrary origins."""
        response = client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Should NOT include the evil origin in allowed origins
        allowed = response.headers.get("access-control-allow-origin", "")
        assert allowed != "*", "CORS must not allow wildcard origins"
        assert "evil.example.com" not in allowed

    def test_cors_allows_localhost(self, client):
        """CORS should allow localhost origins for development."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        allowed = response.headers.get("access-control-allow-origin", "")
        assert allowed == "http://localhost:5173"

    def test_cors_unset_env_uses_defaults(self, tmp_path):
        """Unset ALLOWED_ORIGINS → backend applies localhost default whitelist.

        Isolation: subprocess runs with cwd=tmp_path (outside repo) and
        PYTHONPATH set to backend so app.main imports without triggering
        dotenv discovery of a local .env (which could repopulate ALLOWED_ORIGINS).
        """
        import subprocess
        import sys
        import os as _os
        import json

        backend_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        env = {
            **_os.environ,
            "PYTHONPATH": backend_dir,
            "BELLMARK_SECRET_KEY": "test-secret-cors-regression",
            "BELLMARK_DISABLE_BACKGROUND_RUNS": "1",
            "BELLMARK_DB_PATH": str(tmp_path / "cors_unset.db"),
        }
        env.pop("ALLOWED_ORIGINS", None)

        result = subprocess.run(
            [sys.executable, "-c",
             "import os; os.environ.pop('ALLOWED_ORIGINS', None); "
             "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; "
             "import json; from app.main import ALLOWED_ORIGINS; print(json.dumps(ALLOWED_ORIGINS))"],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
        origins = json.loads(result.stdout.strip().splitlines()[-1])
        assert "http://localhost:5173" in origins
        assert "http://localhost:8000" in origins
        assert origins != []

    def test_cors_sentinel_env_uses_defaults(self, tmp_path):
        """Docker Compose sentinel value → backend maps back to defaults.

        docker-compose.yml uses `${ALLOWED_ORIGINS-__BELLMARK_DEFAULT_CORS__}` so
        unset host vars reach the container as the sentinel string rather than as
        an empty string. Backend must recognize and substitute the default list.
        """
        import subprocess
        import sys
        import os as _os
        import json

        backend_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        env = {
            **_os.environ,
            "PYTHONPATH": backend_dir,
            "BELLMARK_SECRET_KEY": "test-secret-cors-regression",
            "BELLMARK_DISABLE_BACKGROUND_RUNS": "1",
            "BELLMARK_DB_PATH": str(tmp_path / "cors_sentinel.db"),
            "ALLOWED_ORIGINS": "__BELLMARK_DEFAULT_CORS__",
        }

        result = subprocess.run(
            [sys.executable, "-c",
             "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; "
             "import json; from app.main import ALLOWED_ORIGINS; print(json.dumps(ALLOWED_ORIGINS))"],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
        origins = json.loads(result.stdout.strip().splitlines()[-1])
        assert "http://localhost:5173" in origins
        assert origins != []

    def test_cors_explicit_empty_env_locks_down(self, tmp_path):
        """Set-but-empty ALLOWED_ORIGINS → intentional lockdown (allow_origins=[]).

        Isolation: same pattern as test_cors_unset_env_uses_defaults —
        subprocess outside repo, dotenv.load_dotenv stubbed to no-op.
        """
        import subprocess
        import sys
        import os as _os
        import json

        backend_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
        env = {
            **_os.environ,
            "PYTHONPATH": backend_dir,
            "BELLMARK_SECRET_KEY": "test-secret-cors-regression",
            "BELLMARK_DISABLE_BACKGROUND_RUNS": "1",
            "BELLMARK_DB_PATH": str(tmp_path / "cors_empty.db"),
            "ALLOWED_ORIGINS": "",
        }

        result = subprocess.run(
            [sys.executable, "-c",
             "import dotenv; dotenv.load_dotenv = lambda *a, **k: False; "
             "import json; from app.main import ALLOWED_ORIGINS; print(json.dumps(ALLOWED_ORIGINS))"],
            cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, f"subprocess failed: {result.stderr}"
        origins = json.loads(result.stdout.strip().splitlines()[-1])
        assert origins == [], "explicit empty must lock down CORS"


class TestSelfJudging:
    def test_self_judging_rejected(self, client):
        """Benchmark should reject when a model is also used as a judge."""
        model_data = {
            "name": "Test Model",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "model_id": "gpt-4o",
        }
        model_resp = client.post("/api/models/", json=model_data)
        assert model_resp.status_code == 200
        model_id = model_resp.json()["id"]

        benchmark_data = {
            "name": "Self-judge test",
            "model_ids": [model_id],
            "judge_ids": [model_id],  # Same as competitor!
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [{"system_prompt": "", "user_prompt": "Hello"}],
        }
        response = client.post("/api/benchmarks/", json=benchmark_data)
        assert response.status_code == 400
        assert "self-judging" in response.json()["detail"].lower()

    def test_non_overlapping_models_accepted(self, client):
        """Benchmark should accept when models and judges don't overlap."""
        model_resp = client.post("/api/models/", json={
            "name": "Competitor", "provider": "openai",
            "base_url": "https://api.openai.com/v1", "model_id": "gpt-4o",
        })
        judge_resp = client.post("/api/models/", json={
            "name": "Judge", "provider": "anthropic",
            "base_url": "https://api.anthropic.com/v1/messages", "model_id": "claude-sonnet-4-5-20250929",
        })
        model_id = model_resp.json()["id"]
        judge_id = judge_resp.json()["id"]

        benchmark_data = {
            "name": "Valid benchmark",
            "model_ids": [model_id],
            "judge_ids": [judge_id],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            "questions": [{"system_prompt": "", "user_prompt": "Hello"}],
        }
        response = client.post("/api/benchmarks/", json=benchmark_data)
        assert response.status_code == 200


class TestPagination:
    def test_benchmarks_list_default_limit(self, client):
        """Test benchmarks list works with default pagination params."""
        response = client.get("/api/benchmarks/")
        assert response.status_code == 200

    def test_benchmarks_list_with_limit(self, client):
        """Test benchmarks list respects limit and offset params."""
        response = client.get("/api/benchmarks/?limit=10&offset=0")
        assert response.status_code == 200

    def test_models_list_with_limit(self, client):
        """Test models list respects limit param."""
        response = client.get("/api/models/?limit=5")
        assert response.status_code == 200

    def test_models_list_with_offset(self, client):
        """Test models list respects limit and offset params."""
        response = client.get("/api/models/?limit=5&offset=0")
        assert response.status_code == 200

    def test_attachments_list_with_limit(self, client):
        """Test attachments list respects limit param."""
        response = client.get("/api/attachments/?limit=5")
        assert response.status_code == 200

    def test_attachments_list_with_offset(self, client):
        """Test attachments list respects limit and offset params."""
        response = client.get("/api/attachments/?limit=5&offset=0")
        assert response.status_code == 200

    def test_models_pagination_ordering(self, client):
        """Test that models are returned in descending created_at order."""
        # Create multiple models
        for i in range(5):
            client.post("/api/models/", json={
                "name": f"Model {i}",
                "provider": "lmstudio",
                "base_url": "http://localhost:1234/v1/chat/completions",
                "model_id": f"test/model-{i}"
            })

        # Get first 3
        response = client.get("/api/models/?limit=3&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 3

        # Get next 2
        response = client.get("/api/models/?limit=2&offset=3")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2


class TestExportSecurity:
    def _create_benchmark_with_xss_content(self, db):
        """Helper to create benchmark with potentially malicious content directly in DB."""
        from app.db.models import ModelPreset, BenchmarkRun, Question, Generation, Judgment, RunStatus, TaskStatus, JudgeMode

        # Create models with XSS content in names
        models = []
        for i in range(2):
            model = ModelPreset(
                name=f"<script>alert('xss{i}')</script>",
                provider="lmstudio",
                base_url="http://localhost:1234/v1/chat/completions",
                model_id=f"test/xss-{i}"
            )
            db.add(model)
            models.append(model)
        db.commit()

        model_ids = [m.id for m in models]

        # Create benchmark run with XSS content
        run = BenchmarkRun(
            name="<img src=x onerror=alert('name')>",
            status=RunStatus.completed,
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "<script>alert('crit')</script>", "description": "Test", "weight": 1.0}],
            model_ids=model_ids,
            judge_ids=model_ids[:1],
            temperature=0.7
        )
        db.add(run)
        db.commit()

        # Create question with XSS content in prompts
        question = Question(
            benchmark_id=run.id,
            order=0,
            system_prompt="<script>alert('sys')</script>",
            user_prompt="<script>alert('user')</script>"
        )
        db.add(question)
        db.commit()

        # Create generations with XSS content
        for model in models:
            gen = Generation(
                question_id=question.id,
                model_preset_id=model.id,
                content="<script>alert('gen')</script>",
                tokens=10,
                status=TaskStatus.success
            )
            db.add(gen)
        db.commit()

        # Create judgment with XSS content in reasoning
        judgment = Judgment(
            question_id=question.id,
            judge_preset_id=model_ids[0],
            blind_mapping={"A": model_ids[0], "B": model_ids[1]},
            rankings=["A", "B"],
            scores={str(model_ids[0]): {"<script>alert('crit')</script>": 5}, str(model_ids[1]): {"<script>alert('crit')</script>": 3}},
            reasoning="<script>alert('reasoning')</script>",
            status=TaskStatus.success
        )
        db.add(judgment)
        db.commit()

        return run.id

    def test_html_export_escapes_xss(self, client):
        db = next(app.dependency_overrides[get_db]())
        try:
            benchmark_id = self._create_benchmark_with_xss_content(db)
            response = client.get(f"/api/benchmarks/{benchmark_id}/export/html")
            assert response.status_code == 200
            html = response.text
            # Script tags should be escaped, not present as actual tags
            assert "<script>" not in html
            assert "&lt;script&gt;" in html or "alert(" not in html
        finally:
            db.close()


class TestStatisticalEndpoints:
    def _create_test_models(self, client):
        """Create 2 models + 1 judge via API, return (model_ids, judge_id)."""
        models = []
        for name, mid in [("ModelA", "gpt-4"), ("ModelB", "claude-3")]:
            resp = client.post("/api/models/", json={
                "name": name, "provider": "openai", "base_url": "https://api.openai.com/v1/chat/completions", "model_id": mid
            })
            models.append(resp.json()["id"])
        judge_resp = client.post("/api/models/", json={
            "name": "Judge", "provider": "anthropic", "base_url": "https://api.anthropic.com/v1/messages", "model_id": "judge-1"
        })
        return models, judge_resp.json()["id"]

    def _seed_completed_run(self, model_ids, judge_id, n_questions=10):
        """Insert a completed benchmark with judgments directly via ORM."""
        from app.db.models import (
            BenchmarkRun, Question, Generation, Judgment,
            JudgeMode, RunStatus, TaskStatus,
        )
        db = next(app.dependency_overrides[get_db]())
        run = BenchmarkRun(
            name="StatTest", status=RunStatus.completed,
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Quality", "description": "Overall quality", "weight": 1.0}],
            model_ids=model_ids, judge_ids=[judge_id],
        )
        db.add(run)
        db.flush()

        for i in range(n_questions):
            q = Question(benchmark_id=run.id, order=i,
                         system_prompt="You are helpful.", user_prompt=f"Question {i}")
            db.add(q)
            db.flush()
            for mid in model_ids:
                gen = Generation(question_id=q.id, model_preset_id=mid,
                                 content=f"Response from {mid}", tokens=100 + i * 10,
                                 latency_ms=500 + i * 50, status=TaskStatus.success)
                db.add(gen)
            db.flush()
            noise = (i % 3 - 1) * 0.5
            # Vary reasoning length to avoid constant input warnings in bias detection
            reasoning_suffix = " " * (i * 10)  # Add variable whitespace to vary length
            jud = Judgment(
                question_id=q.id, judge_preset_id=judge_id,
                blind_mapping={"A": model_ids[0], "B": model_ids[1]},
                rankings=["A", "B"],
                scores={
                    str(model_ids[0]): {"Quality": 8.0 + noise},
                    str(model_ids[1]): {"Quality": 5.0 + noise},
                },
                reasoning=f"Model A was clearly better.{reasoning_suffix}",
                status=TaskStatus.success, tokens=200, latency_ms=1000,
            )
            db.add(jud)
        db.commit()
        return run.id

    def test_statistics_endpoint(self, client):
        model_ids, judge_id = self._create_test_models(client)
        run_id = self._seed_completed_run(model_ids, judge_id, n_questions=10)
        response = client.get(f"/api/benchmarks/{run_id}/statistics")
        assert response.status_code == 200
        data = response.json()
        assert "model_statistics" in data
        assert "pairwise_comparisons" in data
        assert "power_analysis" in data
        assert len(data["model_statistics"]) == 2
        for ms in data["model_statistics"]:
            assert ms["weighted_score_ci"] is not None
            ci = ms["weighted_score_ci"]
            assert ci["lower"] <= ci["mean"] <= ci["upper"]
        assert len(data["pairwise_comparisons"]) == 1
        comp = data["pairwise_comparisons"][0]
        assert comp["significant"] is True
        assert comp["cohens_d"] > 0.8

    def test_bias_endpoint(self, client):
        model_ids, judge_id = self._create_test_models(client)
        run_id = self._seed_completed_run(model_ids, judge_id)
        response = client.get(f"/api/benchmarks/{run_id}/bias")
        assert response.status_code == 200
        data = response.json()
        assert "position_bias" in data
        assert "length_bias" in data
        assert "self_preference" in data
        assert "verbosity_bias" in data
        assert data["overall_severity"] in ("none", "low", "moderate", "high")

    def test_calibration_endpoint(self, client):
        model_ids, judge_id = self._create_test_models(client)
        run_id = self._seed_completed_run(model_ids, judge_id)
        response = client.get(f"/api/benchmarks/{run_id}/calibration")
        assert response.status_code == 200
        data = response.json()
        assert "judge_reliability" in data
        assert "recommendations" in data
        assert "Judge" in data["judge_reliability"]
        assert data["judge_reliability"]["Judge"]["reliability"] > 0

    def test_elo_leaderboard_after_run(self, client):
        model_ids, judge_id = self._create_test_models(client)
        run_id = self._seed_completed_run(model_ids, judge_id)
        from app.core.elo_service import update_elo_ratings_for_run
        db = next(app.dependency_overrides[get_db]())
        update_elo_ratings_for_run(db, run_id)
        response = client.get("/api/elo/")
        assert response.status_code == 200
        data = response.json()
        assert data["total_models"] == 2
        ratings = data["ratings"]
        assert ratings[0]["model_name"] == "ModelA"
        assert ratings[0]["rating"] > 1500
        assert ratings[1]["rating"] < 1500

    def test_statistics_404_for_missing_run(self, client):
        response = client.get("/api/benchmarks/99999/statistics")
        assert response.status_code == 404

    def test_bias_404_for_missing_run(self, client):
        response = client.get("/api/benchmarks/99999/bias")
        assert response.status_code == 404

    def test_calibration_404_for_missing_run(self, client):
        response = client.get("/api/benchmarks/99999/calibration")
        assert response.status_code == 404
