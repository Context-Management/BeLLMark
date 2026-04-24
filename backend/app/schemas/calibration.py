from pydantic import BaseModel
from typing import Dict, List, Optional


class KappaPair(BaseModel):
    kappa: Optional[float]
    interpretation: str


class JudgeReliability(BaseModel):
    reliability: float
    judgment_count: int
    interpretation: str


class CalibrationReport(BaseModel):
    pairwise_kappa: Dict[str, KappaPair]
    icc: Optional[float]
    icc_interpretation: str
    judge_reliability: Dict[str, JudgeReliability]
    recommendations: List[str]
