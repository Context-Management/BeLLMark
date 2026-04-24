"""Schemas for the cross-benchmark question browser."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

QuestionBrowserMatchMode = Literal["strict", "same-label"]
QuestionBrowserMatchFidelity = Literal["full", "degraded"]
QuestionBrowserEvaluationMode = Literal["comparison", "separate"]
QuestionBrowserPickerFrequencyBand = Literal["all", "high", "medium", "low", "zero"]


class QuestionBrowserPickerGuidanceModel(BaseModel):
    model_preset_id: int
    name: str
    provider: str
    model_id: str
    model_format: Optional[str] = None
    quantization: Optional[str] = None
    is_archived: bool
    is_reasoning: bool
    reasoning_level: Optional[str] = None
    resolved_label: str
    host_label: str

    class Config:
        from_attributes = True


class QuestionBrowserPickerCandidate(QuestionBrowserPickerGuidanceModel):
    active_benchmark_count: int
    selectable: bool


class QuestionBrowserPickerGuidanceResponse(BaseModel):
    selection_state: int
    max_active_count: int
    band_counts: Dict[QuestionBrowserPickerFrequencyBand, int]
    selected_models: List[QuestionBrowserPickerGuidanceModel]
    candidates: List[QuestionBrowserPickerCandidate]

    class Config:
        from_attributes = True


class QuestionBrowserSelectedModel(BaseModel):
    model_preset_id: int
    resolved_label: str
    match_mode: QuestionBrowserMatchMode
    match_identity: Dict[str, Any] = Field(default_factory=dict)
    match_fidelity: QuestionBrowserMatchFidelity
    source_run_id: Optional[int] = None
    source_question_id: Optional[int] = None

    class Config:
        from_attributes = True


class QuestionBrowserSearchRow(BaseModel):
    question_id: int
    run_id: int
    run_name: str
    question_order: int
    prompt_preview: str
    match_fidelity: QuestionBrowserMatchFidelity = "full"

    class Config:
        from_attributes = True


class QuestionBrowserSearchResponse(BaseModel):
    selected_models: List[QuestionBrowserSelectedModel]
    rows: List[QuestionBrowserSearchRow]
    total_count: int
    initial_question_id: Optional[int] = None
    strict_excluded_count: int = 0
    limit: int
    offset: int

    class Config:
        from_attributes = True


class QuestionBrowserCardJudgeGrade(BaseModel):
    judge_preset_id: int
    judge_label: str
    score: Optional[float] = None
    score_rationale: Optional[str] = None
    reasoning: Optional[str] = None
    comments: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


class QuestionBrowserAnswerCard(BaseModel):
    model_preset_id: int
    resolved_label: str
    source_run_id: int
    source_run_name: str
    evaluation_mode: QuestionBrowserEvaluationMode
    run_grade: Optional[float] = None
    question_grade: Optional[float] = None
    judge_grades: List[QuestionBrowserCardJudgeGrade] = Field(default_factory=list)
    tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    speed_tokens_per_second: Optional[float] = None
    estimated_cost: Optional[float] = None
    run_rank: Optional[int] = None
    run_rank_total: Optional[int] = None
    question_rank: Optional[int] = None
    question_rank_total: Optional[int] = None
    answer_text: Optional[str] = None
    judge_opinions: List[str] = Field(default_factory=list)
    match_fidelity: QuestionBrowserMatchFidelity = "full"

    class Config:
        from_attributes = True


class QuestionBrowserDetailResponse(BaseModel):
    question_id: int
    run_id: int
    run_name: str
    question_order: int
    system_prompt: str
    user_prompt: str
    expected_answer: Optional[str] = None
    selected_models: List[QuestionBrowserSelectedModel]
    cards: List[QuestionBrowserAnswerCard]
    source_run_id: Optional[int] = None
    source_question_id: Optional[int] = None

    class Config:
        from_attributes = True
