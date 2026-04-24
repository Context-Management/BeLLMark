"""Pydantic schemas for attachment system."""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from datetime import datetime


class AttachmentResponse(BaseModel):
    """Response schema for attachment metadata."""
    id: int
    filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime

    class Config:
        from_attributes = True


class SuiteAttachmentCreate(BaseModel):
    """Schema for associating attachment with a prompt suite."""
    attachment_id: int
    scope: Literal["all_questions", "specific"] = "all_questions"
    suite_item_order: Optional[int] = None  # Use order, not DB id

    class Config:
        # Validate that scope is one of the allowed values
        json_schema_extra = {
            "example": {
                "attachment_id": 1,
                "scope": "all_questions",
                "suite_item_order": None
            }
        }


class SuiteAttachmentResponse(BaseModel):
    """Response schema for suite attachment with nested attachment data."""
    id: int
    attachment_id: int
    scope: Literal["all_questions", "specific"]
    suite_item_order: Optional[int] = None
    attachment: AttachmentResponse

    class Config:
        from_attributes = True


class QuestionAttachmentInput(BaseModel):
    """For benchmark creation - specifies attachments per question."""
    attachment_ids: List[int] = Field(default_factory=list)  # IMPORTANT: Use Field(default_factory=list), NOT = []

    class Config:
        json_schema_extra = {
            "example": {
                "attachment_ids": [1, 2, 3]
            }
        }
