from pydantic import BaseModel
from typing import Dict, List, Optional


class BiasIndicator(BaseModel):
    name: str
    severity: str
    correlation: Optional[float]
    p_value: Optional[float]
    description: str
    details: Optional[Dict] = None


class BiasReport(BaseModel):
    position_bias: BiasIndicator
    length_bias: BiasIndicator
    self_preference: BiasIndicator
    verbosity_bias: BiasIndicator
    overall_severity: str
    summary: str
