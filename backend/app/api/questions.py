# backend/app/api/questions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import json

from app.db.database import get_db
from app.db.models import ModelPreset, Attachment
from app.schemas.questions import QuestionGenerateRequest, QuestionGenerateResponse, GeneratedQuestion
from app.core.generators import generate
from app.core.attachments import load_attachment_content

router = APIRouter(prefix="/api/questions", tags=["questions"])

GENERATION_PROMPT = '''Generate {count} benchmark questions about: {topic}

{context}

For each question, provide:
1. A system prompt that sets the context for the AI being tested
2. A user prompt that contains the actual question/task

Respond ONLY with a JSON array in this exact format:
[
  {{
    "system_prompt": "You are an expert in...",
    "user_prompt": "Explain..."
  }},
  ...
]

Generate diverse questions that test different aspects of the topic.'''

@router.post("/generate", response_model=QuestionGenerateResponse)
async def generate_questions(
    request: QuestionGenerateRequest,
    db: Session = Depends(get_db)
):
    # Get model preset
    preset = db.query(ModelPreset).filter(ModelPreset.id == request.model_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Model not found")

    # Build context from system_context and/or attachment
    context_parts = []
    if request.system_context:
        context_parts.append(request.system_context)

    if request.context_attachment_id:
        attachment = db.query(Attachment).filter(Attachment.id == request.context_attachment_id).first()
        if not attachment:
            raise HTTPException(status_code=404, detail="Context attachment not found")
        if not attachment.mime_type.startswith("text/"):
            raise HTTPException(status_code=400, detail="Context attachment must be a text file")
        try:
            content_bytes = load_attachment_content(attachment.storage_path)
            file_content = content_bytes.decode("utf-8")
            context_parts.append(f"--- Document: {attachment.filename} ---\n{file_content}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read attachment: {str(e)}")

    context = f"Additional context:\n{chr(10).join(context_parts)}" if context_parts else ""

    prompt = GENERATION_PROMPT.format(
        count=request.count,
        topic=request.topic,
        context=context
    )

    result = await generate(
        preset,
        "You are a benchmark question generator. Generate clear, specific questions for evaluating AI models.",
        prompt
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Generation failed: {result['error']}")

    try:
        # Parse JSON from response
        content = result["content"]
        start = content.find("[")
        end = content.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found in response")

        questions_data = json.loads(content[start:end])
        questions = [
            GeneratedQuestion(
                system_prompt=q["system_prompt"],
                user_prompt=q["user_prompt"]
            )
            for q in questions_data
        ]

        return QuestionGenerateResponse(questions=questions)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse generated questions: {str(e)}")
