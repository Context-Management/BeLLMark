# backend/app/schemas/benchmarks.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime
from app.db.models import JudgeMode, RunStatus, TaskStatus, TemperatureMode

class QuestionCreate(BaseModel):
    system_prompt: str
    user_prompt: str
    expected_answer: str | None = None
    attachment_ids: List[int] = Field(default_factory=list)

class CriterionCreate(BaseModel):
    name: str
    description: str
    weight: float = 1.0

class BenchmarkCreate(BaseModel):
    name: str
    model_ids: List[int]
    judge_ids: List[int]
    judge_mode: JudgeMode
    criteria: List[CriterionCreate]
    questions: List[QuestionCreate]
    temperature: float = 0.7  # Base temperature (used for normalized mode)
    temperature_mode: TemperatureMode = TemperatureMode.normalized
    source_suite_id: int | None = None
    sequential_mode: bool = False
    parent_run_id: int | None = None  # Non-null → spin-off: skip question creation, deep-copy from parent

class BenchmarkStartResponse(BaseModel):
    id: int
    status: str
    warnings: List[Dict] = Field(default_factory=list)

class TopModelEntry(BaseModel):
    name: str
    weighted_score: float

class BenchmarkListResponse(BaseModel):
    id: int
    name: str
    status: RunStatus
    created_at: datetime
    model_count: int
    model_ids: List[int] = []
    judge_count: int
    judge_ids: List[int] = []
    question_count: int
    top_models: List[TopModelEntry] = []  # Top 5 models by weighted score
    total_cost: Optional[float] = None  # Estimated total cost for all generations

    class Config:
        from_attributes = True

class GenerationDetail(BaseModel):
    id: int
    model_preset_id: int
    model_name: str
    content: Optional[str]
    tokens: Optional[int]
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    raw_chars: Optional[int] = None
    answer_chars: Optional[int] = None
    latency_ms: Optional[int] = None
    status: TaskStatus
    error: Optional[str]
    retries: int
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class JudgmentDetail(BaseModel):
    id: int
    judge_preset_id: int
    judge_name: str
    generation_id: Optional[int]
    blind_mapping: Optional[Dict]
    rankings: Optional[List]
    scores: Optional[Dict]
    score_rationales: Optional[Dict[str, str]] = None
    reasoning: Optional[str]
    comments: Optional[Dict] = None  # {model_id: [{text, sentiment}]}
    latency_ms: Optional[int] = None
    tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cached_input_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    status: TaskStatus
    error: Optional[str]
    retries: int
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True

class QuestionAttachmentInfo(BaseModel):
    id: int
    filename: str
    mime_type: str
    inherited: bool  # True if from suite, False if added at run time

    class Config:
        from_attributes = True

class QuestionDetail(BaseModel):
    id: int
    order: int
    system_prompt: str
    user_prompt: str
    expected_answer: str | None = None
    estimated_context_tokens: Optional[int] = None
    attachments: List[QuestionAttachmentInfo] = Field(default_factory=list)
    generations: List[GenerationDetail]
    judgments: List[JudgmentDetail]

    class Config:
        from_attributes = True

class JudgeSummary(BaseModel):
    agreement_rate: float
    disagreement_count: int
    disagreement_questions: List[int]
    per_judge_winners: Dict[str, Dict[str, int]]

class ModelPerformanceMetrics(BaseModel):
    total_tokens: int
    total_latency_ms: int
    tokens_per_second: Optional[float] = None
    estimated_cost: Optional[float] = None  # In USD
    price_input_1m: Optional[float] = None  # $/1M input tokens
    price_output_1m: Optional[float] = None  # $/1M output tokens
    provider: Optional[str] = None


class JudgePerformanceMetrics(BaseModel):
    total_tokens: int
    total_latency_ms: int
    tokens_per_second: Optional[float] = None
    estimated_cost: Optional[float] = None  # In USD
    judgment_count: int = 0

class BenchmarkDetailResponse(BaseModel):
    id: int
    name: str
    status: RunStatus
    judge_mode: JudgeMode
    criteria: List[Dict]
    model_ids: List[int]
    judge_ids: List[int]
    created_at: datetime
    completed_at: Optional[datetime]
    preset_labels: Optional[Dict[int, str]] = None
    questions: List[QuestionDetail]
    run_config_snapshot: Optional[Dict] = None
    source_suite_id: Optional[int] = None
    parent_run_id: Optional[int] = None  # Non-null for spin-off runs
    judge_summary: Optional[JudgeSummary] = None
    performance_metrics: Optional[Dict[str, ModelPerformanceMetrics]] = None  # model_name -> metrics
    judge_metrics: Optional[Dict[str, "JudgePerformanceMetrics"]] = None  # judge_name -> metrics
    comment_summaries: Optional[Dict] = None  # judge_name -> model_name -> summary (string or structured)

    class Config:
        from_attributes = True
