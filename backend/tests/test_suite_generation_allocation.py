"""Tests for suite generation allocation helpers."""

from app.core.suite_pipeline import build_generation_plan, interleave_generated_questions
from app.db.models import ModelPreset, ProviderType


def _preset(name: str, idx: int) -> ModelPreset:
    return ModelPreset(
        id=idx,
        name=name,
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id=f"{name.lower()}/model",
    )


def test_build_generation_plan_balances_counts_and_skips_empty_allocations():
    presets = [_preset("A", 1), _preset("B", 2), _preset("C", 3)]

    plan = build_generation_plan(25, presets)

    assert [count for _, count in plan] == [9, 8, 8]


def test_build_generation_plan_skips_zero_count_entries():
    presets = [_preset("A", 1), _preset("B", 2), _preset("C", 3)]

    plan = build_generation_plan(1, presets)

    assert [preset.name for preset, _ in plan] == ["A"]
    assert [count for _, count in plan] == [1]


def test_interleave_generated_questions_round_robin():
    presets = [_preset("A", 1), _preset("B", 2), _preset("C", 3)]

    combined = interleave_generated_questions([
        (presets[0], [{"user_prompt": "A1"}, {"user_prompt": "A2"}, {"user_prompt": "A3"}]),
        (presets[1], [{"user_prompt": "B1"}, {"user_prompt": "B2"}]),
        (presets[2], [{"user_prompt": "C1"}, {"user_prompt": "C2"}]),
    ])

    assert [item["user_prompt"] for item in combined] == [
        "A1",
        "B1",
        "C1",
        "A2",
        "B2",
        "C2",
        "A3",
    ]
