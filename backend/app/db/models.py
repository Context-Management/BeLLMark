# backend/app/db/models.py
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Enum, Float, Boolean, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum

from .database import Base

class ProviderType(str, enum.Enum):
    lmstudio = "lmstudio"
    openai = "openai"
    anthropic = "anthropic"
    google = "google"
    mistral = "mistral"
    deepseek = "deepseek"
    grok = "grok"
    glm = "glm"
    kimi = "kimi"
    openrouter = "openrouter"
    ollama = "ollama"

class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    summarizing = "summarizing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"

class JudgeMode(str, enum.Enum):
    separate = "separate"
    comparison = "comparison"

class ReasoningLevel(str, enum.Enum):
    none = "none"      # No reasoning (instant mode)
    low = "low"        # Minimal reasoning
    medium = "medium"  # Moderate reasoning
    high = "high"      # Full reasoning
    xhigh = "xhigh"    # Extended reasoning (OpenAI only)
    max = "max"        # Maximum reasoning (Anthropic Opus 4.6)

class TaskStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"

class TemperatureMode(str, enum.Enum):
    normalized = "normalized"  # Semantically equivalent across providers
    provider_default = "provider_default"  # Use each provider's recommended default
    custom = "custom"  # Use custom temperature per model preset

class ModelPreset(Base):
    __tablename__ = "model_presets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    provider = Column(Enum(ProviderType), nullable=False)
    base_url = Column(String(500), nullable=False)
    model_id = Column(String(200), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    # Pricing override (nullable = use provider defaults)
    price_input = Column(Float, nullable=True)   # $/1M input tokens
    price_output = Column(Float, nullable=True)  # $/1M output tokens
    price_source = Column(String(50), nullable=True)
    price_source_url = Column(String(500), nullable=True)
    price_checked_at = Column(DateTime, nullable=True)
    price_currency = Column(String(10), nullable=True)
    supports_vision = Column(Integer, nullable=True)  # 1=yes, 0=no, NULL=unknown (falls back to provider default)
    context_limit = Column(Integer, nullable=True)  # Max input tokens (nullable = use provider default)
    # Reasoning configuration
    is_reasoning = Column(Integer, default=0)  # 1 if reasoning/thinking enabled
    reasoning_level = Column(Enum(ReasoningLevel), nullable=True)  # Reasoning effort level
    # Custom temperature (used when TemperatureMode.custom is selected)
    custom_temperature = Column(Float, nullable=True)  # 0.0-2.0, null = use mode default
    is_archived = Column(Integer, default=0)  # 1 = soft-deleted (hidden from UI, data preserved)
    # Quantization metadata (auto-detected from discovery, user-overridable)
    quantization = Column(String(50), nullable=True)    # e.g. Q4_K_M, 4bit, MXFP4
    model_format = Column(String(50), nullable=True)    # e.g. GGUF, MLX, GPTQ, AWQ
    model_source = Column(String(100), nullable=True)   # e.g. mlx-community, lmstudio-community
    parameter_count = Column(String(50), nullable=True)
    quantization_bits = Column(Float, nullable=True)
    selected_variant = Column(String(255), nullable=True)
    model_architecture = Column(String(100), nullable=True)
    reasoning_detection_source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class BenchmarkRun(Base):
    __tablename__ = "benchmark_runs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    status = Column(Enum(RunStatus), default=RunStatus.pending)
    judge_mode = Column(Enum(JudgeMode), nullable=False)
    criteria = Column(JSON, nullable=False)  # [{name, description, weight}]
    model_ids = Column(JSON, nullable=False)  # [model_preset_id, ...]
    judge_ids = Column(JSON, nullable=False)  # [model_preset_id, ...]
    temperature = Column(Float, default=0.7)  # Base temperature (used for normalized/custom fallback)
    temperature_mode = Column(Enum(TemperatureMode), default=TemperatureMode.normalized)
    run_config_snapshot = Column(JSON, nullable=True)
    source_suite_id = Column(Integer, ForeignKey("prompt_suites.id"), nullable=True)
    parent_run_id = Column(Integer, ForeignKey("benchmark_runs.id"), nullable=True, index=True)
    random_seed = Column(Integer, nullable=True)  # Random seed for reproducibility
    total_context_tokens = Column(Integer, nullable=True)  # Sum across all questions
    comment_summaries = Column(JSON, nullable=True)  # {judge_name: {model_name: "summary"}}
    sequential_mode = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    questions = relationship("Question", back_populates="benchmark")
    parent_run = relationship("BenchmarkRun", remote_side="BenchmarkRun.id", foreign_keys="BenchmarkRun.parent_run_id")

class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    benchmark_id = Column(Integer, ForeignKey("benchmark_runs.id"), nullable=False, index=True)
    order = Column(Integer, nullable=False)
    system_prompt = Column(Text, nullable=False)
    user_prompt = Column(Text, nullable=False)
    context_tokens = Column(Integer, nullable=True)  # Input tokens used for this question
    expected_answer = Column(Text, nullable=True)

    benchmark = relationship("BenchmarkRun", back_populates="questions")
    generations = relationship("Generation", back_populates="question")
    judgments = relationship("Judgment", back_populates="question")

class Generation(Base):
    __tablename__ = "generations"
    __table_args__ = (
        Index("ix_generations_model_preset_id_question_id", "model_preset_id", "question_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    model_preset_id = Column(Integer, ForeignKey("model_presets.id"), nullable=False, index=True)
    content = Column(Text, nullable=True)
    tokens = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    raw_chars = Column(Integer, nullable=True)  # Character count before stripping thinking
    answer_chars = Column(Integer, nullable=True)  # Character count after stripping thinking
    latency_ms = Column(Integer, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.pending)
    error = Column(Text, nullable=True)
    retries = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)    # Set when status -> running
    completed_at = Column(DateTime, nullable=True)
    model_version = Column(String(200), nullable=True)  # Model version from API response header

    question = relationship("Question", back_populates="generations")
    model_preset = relationship("ModelPreset")

class Judgment(Base):
    __tablename__ = "judgments"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    judge_preset_id = Column(Integer, ForeignKey("model_presets.id"), nullable=False, index=True)
    generation_id = Column(Integer, ForeignKey("generations.id"), nullable=True, index=True)  # For separate mode
    blind_mapping = Column(JSON, nullable=True)  # {"A": model_id, "B": model_id}
    presentation_mapping = Column(JSON, nullable=True)  # {"1": "A", "2": "C", "3": "B"} — actual order shown to judge
    rankings = Column(JSON, nullable=True)  # ["A", "B", "C"] or null for separate
    scores = Column(JSON, nullable=True)  # {model_id: {criterion: score}}
    reasoning = Column(Text, nullable=True)
    comments = Column(JSON, nullable=True)  # {model_id: [{text, sentiment}]}
    score_rationales = Column(JSON, nullable=True)  # {model_id: "1-3 sentence rationale"}
    latency_ms = Column(Integer, nullable=True)
    tokens = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cached_input_tokens = Column(Integer, nullable=True)
    reasoning_tokens = Column(Integer, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.pending)
    error = Column(Text, nullable=True)
    retries = Column(Integer, default=0)
    completed_at = Column(DateTime, nullable=True)
    judge_temperature = Column(Float, nullable=True)  # Temperature used for this judgment

    question = relationship("Question", back_populates="judgments")
    judge_preset = relationship("ModelPreset")
    generation = relationship("Generation")

class PromptSuite(Base):
    __tablename__ = "prompt_suites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    default_criteria = Column(JSON, nullable=True)
    generation_metadata = Column(JSON, nullable=True)
    coverage_report = Column(JSON, nullable=True)
    dedupe_report = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    items = relationship("PromptSuiteItem", back_populates="suite", order_by="PromptSuiteItem.order")


class SuiteGenerationJob(Base):
    __tablename__ = "suite_generation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(Enum(RunStatus), default=RunStatus.pending, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    topic = Column(Text, nullable=False)
    count = Column(Integer, nullable=False)
    generator_model_ids = Column(JSON, nullable=False)
    editor_model_id = Column(Integer, ForeignKey("model_presets.id"), nullable=False)
    reviewer_model_ids = Column(JSON, nullable=False)
    pipeline_config = Column(JSON, nullable=False)
    coverage_mode = Column(String(50), nullable=False, default="none")
    coverage_spec = Column(JSON, nullable=True)
    max_topics_per_question = Column(Integer, nullable=False, default=1)
    context_attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=True)
    phase = Column(String(50), nullable=True)
    snapshot_payload = Column(JSON, nullable=True)
    checkpoint_payload = Column(JSON, nullable=True)
    suite_id = Column(Integer, ForeignKey("prompt_suites.id"), nullable=True)
    partial_suite_id = Column(Integer, ForeignKey("prompt_suites.id"), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)

    editor_model = relationship("ModelPreset", foreign_keys=[editor_model_id])
    context_attachment = relationship("Attachment", foreign_keys=[context_attachment_id])
    suite = relationship("PromptSuite", foreign_keys=[suite_id])
    partial_suite = relationship("PromptSuite", foreign_keys=[partial_suite_id])

class PromptSuiteItem(Base):
    __tablename__ = "prompt_suite_items"

    id = Column(Integer, primary_key=True, index=True)
    suite_id = Column(Integer, ForeignKey("prompt_suites.id"), index=True)
    order = Column(Integer)
    system_prompt = Column(String)
    user_prompt = Column(String)
    expected_answer = Column(Text, nullable=True)
    category = Column(String, nullable=True)
    difficulty = Column(String, nullable=True)
    criteria = Column(JSON, nullable=True)
    coverage_topic_ids = Column(JSON, nullable=True)
    coverage_topic_labels = Column(JSON, nullable=True)
    generation_slot_index = Column(Integer, nullable=True)

    suite = relationship("PromptSuite", back_populates="items")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)  # Original filename
    storage_path = Column(String(500), nullable=False)  # Relative path in uploads/
    mime_type = Column(String(100), nullable=False)  # text/plain, image/png, etc.
    size_bytes = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SuiteAttachmentScope(str, enum.Enum):
    all_questions = "all_questions"
    specific = "specific"


class SuiteAttachment(Base):
    __tablename__ = "suite_attachments"

    id = Column(Integer, primary_key=True, index=True)
    suite_id = Column(Integer, ForeignKey("prompt_suites.id"), nullable=False, index=True)
    attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=False, index=True)
    scope = Column(Enum(SuiteAttachmentScope), default=SuiteAttachmentScope.all_questions)
    suite_item_id = Column(Integer, ForeignKey("prompt_suite_items.id"), nullable=True)

    suite = relationship("PromptSuite")
    attachment = relationship("Attachment")
    suite_item = relationship("PromptSuiteItem")


class QuestionAttachment(Base):
    __tablename__ = "question_attachments"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    attachment_id = Column(Integer, ForeignKey("attachments.id"), nullable=False, index=True)
    inherited = Column(Integer, default=0)  # 1 if came from suite, 0 if added at run time

    question = relationship("Question")
    attachment = relationship("Attachment")


class EloRating(Base):
    __tablename__ = "elo_ratings"
    id = Column(Integer, primary_key=True, index=True)
    model_preset_id = Column(Integer, ForeignKey("model_presets.id"), nullable=False, unique=True, index=True)
    rating = Column(Float, default=1500.0)
    uncertainty = Column(Float, default=350.0)
    games_played = Column(Integer, default=0)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    model_preset = relationship("ModelPreset")


class EloHistory(Base):
    __tablename__ = "elo_history"
    id = Column(Integer, primary_key=True, index=True)
    model_preset_id = Column(Integer, ForeignKey("model_presets.id"), nullable=False, index=True)
    benchmark_run_id = Column(Integer, ForeignKey("benchmark_runs.id"), nullable=False, index=True)
    rating_before = Column(Float, nullable=False)
    rating_after = Column(Float, nullable=False)
    games_in_run = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    model_preset = relationship("ModelPreset")
    benchmark_run = relationship("BenchmarkRun")


class ConcurrencySetting(Base):
    __tablename__ = "concurrency_settings"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String(50), nullable=False)
    server_key = Column(String(500), nullable=True)
    max_concurrency = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint('provider', 'server_key', name='uq_concurrency_provider_server'),
    )
