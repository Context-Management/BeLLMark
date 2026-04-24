# backend/tests/test_reasoning_integration.py
"""Integration tests for reasoning model workflow."""

import pytest


def test_full_reasoning_model_flow(client):
    """Test creating and using a reasoning model end-to-end."""
    # 1. Create a reasoning model
    create_resp = client.post("/api/models/", json={
        "name": "GPT-5.2 High Reasoning Test",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model_id": "gpt-5.2",
        "is_reasoning": True,
        "reasoning_level": "high"
    })
    assert create_resp.status_code == 200
    model = create_resp.json()
    model_id = model["id"]

    # 2. Verify it's returned correctly in list
    list_resp = client.get("/api/models/")
    assert list_resp.status_code == 200
    models = list_resp.json()
    found = next((m for m in models if m["id"] == model_id), None)
    assert found is not None
    assert found["is_reasoning"] is True
    assert found["reasoning_level"] == "high"

    # 3. Update reasoning level
    update_resp = client.put(f"/api/models/{model_id}", json={
        "reasoning_level": "xhigh"
    })
    assert update_resp.status_code == 200
    assert update_resp.json()["reasoning_level"] == "xhigh"

    # 4. Clean up
    delete_resp = client.delete(f"/api/models/{model_id}")
    assert delete_resp.status_code == 200


def test_create_non_reasoning_model(client):
    """Test creating a model without reasoning enabled."""
    create_resp = client.post("/api/models/", json={
        "name": "GPT-4o Standard Test",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1/chat/completions",
        "model_id": "gpt-4o",
        "is_reasoning": False
    })
    assert create_resp.status_code == 200
    model = create_resp.json()
    assert model["is_reasoning"] is False
    assert model["reasoning_level"] is None

    # Clean up
    client.delete(f"/api/models/{model['id']}")


def test_reasoning_level_options(client):
    """Test all valid reasoning levels."""
    levels = ["none", "low", "medium", "high", "xhigh"]
    created_ids = []

    for level in levels:
        resp = client.post("/api/models/", json={
            "name": f"Reasoning Test {level}",
            "provider": "openai",
            "base_url": "https://api.openai.com/v1/chat/completions",
            "model_id": "gpt-5.2",
            "is_reasoning": True,
            "reasoning_level": level
        })
        assert resp.status_code == 200
        model = resp.json()
        assert model["reasoning_level"] == level
        created_ids.append(model["id"])

    # Clean up
    for model_id in created_ids:
        client.delete(f"/api/models/{model_id}")


def test_toggle_reasoning_on_existing_model(client):
    """Test enabling reasoning on an existing non-reasoning model."""
    # Create without reasoning
    create_resp = client.post("/api/models/", json={
        "name": "Toggle Reasoning Test",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "model_id": "deepseek-chat",
        "is_reasoning": False
    })
    assert create_resp.status_code == 200
    model_id = create_resp.json()["id"]

    # Enable reasoning
    update_resp = client.put(f"/api/models/{model_id}", json={
        "is_reasoning": True,
        "reasoning_level": "medium"
    })
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["is_reasoning"] is True
    assert updated["reasoning_level"] == "medium"

    # Clean up
    client.delete(f"/api/models/{model_id}")
