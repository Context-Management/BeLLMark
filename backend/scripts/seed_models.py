#!/usr/bin/env python3
"""
Seed script to create/update model presets with correct reasoning configuration.
Run with: cd backend && source .venv/bin/activate && python -m scripts.seed_models
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import SessionLocal
from app.db.models import ModelPreset, ProviderType, ReasoningLevel

# Model definitions: (name, provider, model_id, is_reasoning, reasoning_level)
MODEL_PRESETS = [
    # OpenAI - Non-reasoning
    ("GPT-5.3 Codex", "openai", "gpt-5.3-codex", False, None),
    ("GPT-5.2", "openai", "gpt-5.2", False, None),
    ("GPT-5.2 Codex", "openai", "gpt-5.2-codex", False, None),
    ("GPT-5 Mini", "openai", "gpt-5-mini", False, None),
    ("GPT-5 Nano", "openai", "gpt-5-nano", False, None),
    ("GPT-4o", "openai", "gpt-4o", False, None),
    ("GPT-4o Mini", "openai", "gpt-4o-mini", False, None),
    # OpenAI - Reasoning variants
    ("GPT-5.3 Codex (Low Reasoning)", "openai", "gpt-5.3-codex", True, "low"),
    ("GPT-5.3 Codex (Medium Reasoning)", "openai", "gpt-5.3-codex", True, "medium"),
    ("GPT-5.3 Codex (High Reasoning)", "openai", "gpt-5.3-codex", True, "high"),
    ("GPT-5.3 Codex (XHigh Reasoning)", "openai", "gpt-5.3-codex", True, "xhigh"),
    ("GPT-5.2 (Low Reasoning)", "openai", "gpt-5.2", True, "low"),
    ("GPT-5.2 (Medium Reasoning)", "openai", "gpt-5.2", True, "medium"),
    ("GPT-5.2 (High Reasoning)", "openai", "gpt-5.2", True, "high"),
    ("o1", "openai", "o1", True, "high"),
    ("o1 Mini", "openai", "o1-mini", True, "medium"),

    # Anthropic - Standard (no extended thinking)
    ("Claude Opus 4.7", "anthropic", "claude-opus-4-7", False, None),
    ("Claude Opus 4.6", "anthropic", "claude-opus-4-6", False, None),
    ("Claude Opus 4.5", "anthropic", "claude-opus-4-5", False, None),
    ("Claude Sonnet 4.5", "anthropic", "claude-sonnet-4-5", False, None),
    ("Claude Haiku 4.5", "anthropic", "claude-haiku-4-5", False, None),
    # Anthropic - Extended Thinking (budget_tokens)
    ("Claude Opus 4.7 (Low Thinking)", "anthropic", "claude-opus-4-7", True, "low"),
    ("Claude Opus 4.7 (Medium Thinking)", "anthropic", "claude-opus-4-7", True, "medium"),
    ("Claude Opus 4.7 (High Thinking)", "anthropic", "claude-opus-4-7", True, "high"),
    ("Claude Opus 4.7 (Max Thinking)", "anthropic", "claude-opus-4-7", True, "max"),
    ("Claude Opus 4.6 (Low Thinking)", "anthropic", "claude-opus-4-6", True, "low"),
    ("Claude Opus 4.6 (Medium Thinking)", "anthropic", "claude-opus-4-6", True, "medium"),
    ("Claude Opus 4.6 (High Thinking)", "anthropic", "claude-opus-4-6", True, "high"),
    ("Claude Opus 4.6 (Max Thinking)", "anthropic", "claude-opus-4-6", True, "max"),
    ("Claude Opus 4.5 (Low Thinking)", "anthropic", "claude-opus-4-5", True, "low"),
    ("Claude Opus 4.5 (Medium Thinking)", "anthropic", "claude-opus-4-5", True, "medium"),
    ("Claude Opus 4.5 (High Thinking)", "anthropic", "claude-opus-4-5", True, "high"),
    ("Claude Sonnet 4.5 (Low Thinking)", "anthropic", "claude-sonnet-4-5", True, "low"),
    ("Claude Sonnet 4.5 (Medium Thinking)", "anthropic", "claude-sonnet-4-5", True, "medium"),
    ("Claude Sonnet 4.5 (High Thinking)", "anthropic", "claude-sonnet-4-5", True, "high"),
    ("Claude Haiku 4.5 (Low Thinking)", "anthropic", "claude-haiku-4-5", True, "low"),
    ("Claude Haiku 4.5 (High Thinking)", "anthropic", "claude-haiku-4-5", True, "high"),

    # Google - Non-reasoning
    ("Gemini 3 Pro Preview", "google", "gemini-3-pro-preview", False, None),
    ("Gemini 3 Flash Preview", "google", "gemini-3-flash-preview", False, None),
    ("Gemini 2.5 Pro", "google", "gemini-2.5-pro", False, None),
    ("Gemini 2.5 Flash", "google", "gemini-2.5-flash", False, None),
    # Google - Reasoning (thinking_level)
    ("Gemini 3 Pro (Low Thinking)", "google", "gemini-3-pro-preview", True, "low"),
    ("Gemini 3 Pro (High Thinking)", "google", "gemini-3-pro-preview", True, "high"),
    ("Gemini 3 Flash (Low Thinking)", "google", "gemini-3-flash-preview", True, "low"),
    ("Gemini 3 Flash (High Thinking)", "google", "gemini-3-flash-preview", True, "high"),

    # DeepSeek - Non-reasoning
    ("DeepSeek V3.2 Chat", "deepseek", "deepseek-chat", False, None),
    # DeepSeek - Reasoning (thinking: {type: "enabled"})
    ("DeepSeek V3.2 (Thinking)", "deepseek", "deepseek-chat", True, "high"),
    ("DeepSeek R1 Reasoner", "deepseek", "deepseek-reasoner", True, "high"),

    # Grok - Note: Grok 4 always reasons at max capacity (no param supported)
    ("Grok 4", "grok", "grok-4", True, "high"),  # Always max reasoning
    ("Grok 4 Fast", "grok", "grok-4-fast", False, None),
    ("Grok 4.1 Fast", "grok", "grok-4-1-fast", False, None),
    ("Grok 4.1 Fast (Reasoning)", "grok", "grok-4-1-fast", True, "high"),
    ("Grok 3", "grok", "grok-3", False, None),

    # GLM - Standard (instant mode)
    ("GLM-4.7", "glm", "glm-4.7", False, None),
    ("GLM-4.7 Flash", "glm", "glm-4.7-flash", False, None),
    ("GLM-4.7 FlashX", "glm", "glm-4.7-flashx", False, None),
    ("GLM-4.6V", "glm", "glm-4.6v", False, None),
    # GLM - Thinking mode (thinking: {type: "enabled"})
    ("GLM-4.7 (Thinking)", "glm", "glm-4.7", True, "high"),
    ("GLM-4.7 Flash (Thinking)", "glm", "glm-4.7-flash", True, "high"),

    # Kimi - Non-reasoning (instant mode)
    ("Kimi K2.5", "kimi", "kimi-k2.5", False, None),
    # Kimi - Reasoning (thinking mode)
    ("Kimi K2.5 (Thinking)", "kimi", "kimi-k2.5", True, "high"),

    # Mistral - Standard models (using -latest aliases for auto-updates)
    ("Mistral Large 3", "mistral", "mistral-large-latest", False, None),
    ("Mistral Medium 3.1", "mistral", "mistral-medium-latest", False, None),
    ("Mistral Small 3.2", "mistral", "mistral-small-latest", False, None),
    ("Codestral", "mistral", "codestral-latest", False, None),
    ("Devstral 2", "mistral", "devstral-latest", False, None),
    # Mistral - Magistral reasoning models (prompt_mode: "reasoning")
    ("Magistral Small", "mistral", "magistral-small-latest", True, "high"),
    ("Magistral Medium", "mistral", "magistral-medium-latest", True, "high"),

    # LM Studio - Local models (example)
    ("Qwen3 Coder Next", "lmstudio", "qwen3-coder-next", False, None),
    ("Solar Open 100B", "lmstudio", "solar-open-100b", False, None),
]

BASE_URLS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "grok": "https://api.x.ai/v1/chat/completions",
    "glm": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    "kimi": "https://api.moonshot.ai/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "lmstudio": "http://localhost:1234/v1/chat/completions",
}


def main():
    db = SessionLocal()
    try:
        created = 0
        updated = 0

        # First, collect existing API keys by provider
        provider_keys: dict[str, bytes | None] = {}
        existing_models = db.query(ModelPreset).all()
        for m in existing_models:
            if m.api_key_encrypted and m.provider.value not in provider_keys:
                provider_keys[m.provider.value] = m.api_key_encrypted
                print(f"Found API key for {m.provider.value}")

        for name, provider, model_id, is_reasoning, reasoning_level in MODEL_PRESETS:
            # Check if exists by name
            existing = db.query(ModelPreset).filter(ModelPreset.name == name).first()

            provider_enum = ProviderType(provider)
            level_enum = ReasoningLevel(reasoning_level) if reasoning_level else None
            base_url = BASE_URLS.get(provider, "")
            api_key = provider_keys.get(provider)  # Inherit key from provider

            if existing:
                # Update existing (preserve API key if set)
                existing.provider = provider_enum
                existing.model_id = model_id
                existing.is_reasoning = is_reasoning
                existing.reasoning_level = level_enum
                if not existing.base_url:
                    existing.base_url = base_url
                if not existing.api_key_encrypted and api_key:
                    existing.api_key_encrypted = api_key
                updated += 1
                print(f"Updated: {name}")
            else:
                # Create new with inherited API key
                preset = ModelPreset(
                    name=name,
                    provider=provider_enum,
                    base_url=base_url,
                    model_id=model_id,
                    api_key_encrypted=api_key,
                    is_reasoning=is_reasoning,
                    reasoning_level=level_enum,
                )
                db.add(preset)
                created += 1
                print(f"Created: {name}")

        db.commit()
        print(f"\nDone! Created: {created}, Updated: {updated}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
