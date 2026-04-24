from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class EloRatingResponse(BaseModel):
    model_id: int
    model_name: str
    provider: str
    rating: float
    uncertainty: float
    games_played: int
    updated_at: Optional[datetime]
    is_reasoning: bool = False
    reasoning_level: Optional[str] = None

    class Config:
        from_attributes = True


class EloHistoryPoint(BaseModel):
    benchmark_run_id: int
    run_name: str
    rating_before: float
    rating_after: float
    games_in_run: int
    created_at: datetime

    class Config:
        from_attributes = True


class EloLeaderboardResponse(BaseModel):
    ratings: List[EloRatingResponse]
    total_models: int


class AggregateModelEntry(BaseModel):
    model_preset_id: int
    model_name: str
    provider: str
    questions_won: int
    questions_lost: int
    questions_tied: int
    total_questions: int
    win_rate: Optional[float]  # null if total_questions == 0
    avg_weighted_score: Optional[float]  # null if scored_questions == 0
    scored_questions: int
    runs_participated: int
    is_reasoning: bool = False
    reasoning_level: Optional[str] = None


class AggregateLeaderboardResponse(BaseModel):
    models: List[AggregateModelEntry]
