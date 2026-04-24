# backend/app/schemas/questions.py
from pydantic import BaseModel, Field
from typing import List, Optional

class QuestionGenerateRequest(BaseModel):
    model_id: int  # Model preset to use for generation
    topic: str  # Topic for the questions
    count: int = Field(ge=1, le=50, default=5)
    system_context: Optional[str] = None  # Optional context for system prompt
    context_attachment_id: Optional[int] = None  # Attachment to use as context

class GeneratedQuestion(BaseModel):
    system_prompt: str
    user_prompt: str

class QuestionGenerateResponse(BaseModel):
    questions: List[GeneratedQuestion]
