from pydantic import BaseModel
from typing import Dict, List, Optional


class ConfidenceInterval(BaseModel):
    lower: float
    mean: float
    upper: float


class PairwiseComparison(BaseModel):
    model_a: str
    model_b: str
    score_diff: float
    cohens_d: Optional[float]
    p_value: Optional[float]
    adjusted_p: Optional[float]
    significant: bool
    effect_label: str


class ModelStatistics(BaseModel):
    model_name: str
    weighted_score_ci: Optional[ConfidenceInterval]
    per_criterion_ci: Dict[str, ConfidenceInterval]
    win_rate: float
    win_rate_ci: Optional[ConfidenceInterval]


class PowerAnalysisResult(BaseModel):
    current_questions: int
    recommended_small_effect: int
    recommended_medium_effect: int
    recommended_large_effect: int
    adequate_for: str


class RunStatisticsResponse(BaseModel):
    model_statistics: List[ModelStatistics]
    pairwise_comparisons: List[PairwiseComparison]
    power_analysis: PowerAnalysisResult
    sample_size_warning: Optional[str]
