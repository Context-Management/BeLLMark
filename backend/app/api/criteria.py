# backend/app/api/criteria.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import json

from app.db.database import get_db
from app.db.models import ModelPreset, Attachment
from app.core.generators import generate
from app.core.attachments import load_attachment_content

router = APIRouter(prefix="/api/criteria", tags=["criteria"])

class QuestionContext(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""
    attachment_ids: List[int] = []

class CriteriaGenerateRequest(BaseModel):
    model_id: int
    topic: str = ""
    count: int = 4
    questions: List[QuestionContext] = []
    global_attachment_ids: List[int] = []

class Criterion(BaseModel):
    name: str
    description: str
    weight: int

class CriteriaGenerateResponse(BaseModel):
    criteria: List[Criterion]

CRITERIA_PROMPT_WITH_TOPIC = '''Generate {count} evaluation criteria for judging LLM responses about: {topic}

{context_section}
Each criterion should have:
- name: Short name (1-3 words)
- description: What to evaluate (1 sentence)
- weight: Importance 1-5 (5 = most important)

Design criteria that are specifically relevant to the questions and content being evaluated.

Respond in this exact JSON format:
{{
    "criteria": [
        {{"name": "Accuracy", "description": "Factual correctness and precision", "weight": 5}},
        {{"name": "Clarity", "description": "Clear and understandable explanation", "weight": 4}}
    ]
}}'''

CRITERIA_PROMPT_NO_TOPIC = '''Generate {count} evaluation criteria for judging LLM responses to the following questions and content.

{context_section}
Each criterion should have:
- name: Short name (1-3 words)
- description: What to evaluate (1 sentence)
- weight: Importance 1-5 (5 = most important)

Design criteria that are specifically relevant to these questions and any attached content.

Respond in this exact JSON format:
{{
    "criteria": [
        {{"name": "Accuracy", "description": "Factual correctness and precision", "weight": 5}},
        {{"name": "Clarity", "description": "Clear and understandable explanation", "weight": 4}}
    ]
}}'''


def _build_context_section(questions: List[QuestionContext], global_attachment_ids: List[int], db: Session) -> str:
    """Build a context section describing the questions and attachments."""
    parts = []

    # Collect all unique attachment IDs
    all_attachment_ids = set(global_attachment_ids)
    for q in questions:
        all_attachment_ids.update(q.attachment_ids)

    # Load attachment metadata and text content
    attachment_summaries = []
    if all_attachment_ids:
        attachments = db.query(Attachment).filter(Attachment.id.in_(all_attachment_ids)).all()
        for att in attachments:
            if att.mime_type.startswith("text/") or att.filename.endswith((".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html", ".xml")):
                try:
                    content = load_attachment_content(att.storage_path)
                    text = content.decode("utf-8", errors="replace")
                    # Truncate long files to keep prompt reasonable
                    if len(text) > 2000:
                        text = text[:2000] + "\n... (truncated)"
                    attachment_summaries.append(f"[Attached file: {att.filename}]\n{text}")
                except Exception:
                    attachment_summaries.append(f"[Attached file: {att.filename} (could not read)]")
            elif att.mime_type.startswith("image/"):
                attachment_summaries.append(f"[Attached image: {att.filename}]")
            else:
                attachment_summaries.append(f"[Attached file: {att.filename} ({att.mime_type})]")

    # Build questions section
    if questions:
        parts.append("The benchmark includes these questions/prompts:")
        for i, q in enumerate(questions, 1):
            q_parts = []
            if q.system_prompt.strip():
                q_parts.append(f"  System: {q.system_prompt.strip()}")
            if q.user_prompt.strip():
                q_parts.append(f"  User: {q.user_prompt.strip()}")
            if q_parts:
                parts.append(f"\nQuestion {i}:")
                parts.extend(q_parts)

    # Add attachment summaries
    if attachment_summaries:
        parts.append("\nAttached content:")
        parts.extend(attachment_summaries)

    if not parts:
        return ""

    return "\n".join(parts) + "\n"


@router.post("/generate", response_model=CriteriaGenerateResponse)
async def generate_criteria(request: CriteriaGenerateRequest, db: Session = Depends(get_db)):
    model = db.query(ModelPreset).filter(ModelPreset.id == request.model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    context_section = _build_context_section(request.questions, request.global_attachment_ids, db)

    if request.topic.strip():
        prompt = CRITERIA_PROMPT_WITH_TOPIC.format(
            count=request.count, topic=request.topic, context_section=context_section
        )
    else:
        if not context_section:
            raise HTTPException(status_code=400, detail="Provide either a topic or questions to generate criteria from")
        prompt = CRITERIA_PROMPT_NO_TOPIC.format(
            count=request.count, context_section=context_section
        )

    try:
        result = await generate(
            model,
            "You are an expert at designing evaluation criteria for LLM benchmarks.",
            prompt
        )
    except Exception as e:
        print(f"[CRITERIA] Generation exception for {model.name}: {e}")
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

    if not result["success"]:
        error_msg = result.get("error", "Generation failed")
        print(f"[CRITERIA] Generation failed for {model.name}: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

    try:
        content = result["content"]
        # Extract JSON from response (may have extra text)
        start = content.find("{")
        end = content.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found in response")

        data = json.loads(content[start:end])
        return CriteriaGenerateResponse(criteria=data["criteria"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse response: {str(e)}")
