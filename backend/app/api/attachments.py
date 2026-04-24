import os
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import Attachment, SuiteAttachment, QuestionAttachment
from app.schemas.attachments import AttachmentResponse

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

# Configurable upload directory
UPLOAD_DIR = os.environ.get("BELLMARK_UPLOAD_DIR", "uploads/attachments")
ALLOWED_EXTENSIONS = {".txt", ".md", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_TEXT_SIZE = 1 * 1024 * 1024  # 1MB for text files
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB for images

def get_upload_dir():
    """Ensure upload directory exists and return path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    return UPLOAD_DIR

@router.post("/", response_model=AttachmentResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a file attachment."""
    # Validate extension
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type {ext} not allowed. Allowed: {ALLOWED_EXTENSIONS}")

    # Determine size limit before reading
    is_image = ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    max_size = MAX_IMAGE_SIZE if is_image else MAX_TEXT_SIZE

    # Stream file content with size enforcement (reject before fully buffering)
    chunks = []
    received = 0
    while True:
        chunk = await file.read(65536)  # 64KB chunks
        if not chunk:
            break
        received += len(chunk)
        if received > max_size:
            raise HTTPException(413, f"File too large. Max: {max_size // (1024*1024)}MB")
        chunks.append(chunk)
    content = b"".join(chunks)
    size = received

    # Generate unique filename (store only filename, not full path)
    unique_name = f"{uuid.uuid4().hex}{ext}"
    full_path = os.path.join(get_upload_dir(), unique_name)

    # Write file
    try:
        with open(full_path, "wb") as f:
            f.write(content)
    except IOError as e:
        raise HTTPException(500, f"Failed to write file: {str(e)}")

    # Determine MIME type
    mime_types = {
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(ext, "application/octet-stream")

    # Create DB record (store only filename, not full path)
    attachment = Attachment(
        filename=file.filename or "unnamed",
        storage_path=unique_name,  # Relative path only
        mime_type=mime_type,
        size_bytes=size
    )
    try:
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
    except Exception as e:
        # Clean up orphaned file on DB failure
        if os.path.exists(full_path):
            os.remove(full_path)
        raise HTTPException(500, f"Database error: {str(e)}")

    return attachment

@router.get("/", response_model=List[AttachmentResponse])
def list_attachments(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List all attachments with pagination."""
    return db.query(Attachment).order_by(Attachment.created_at.desc()).offset(offset).limit(limit).all()

@router.get("/{attachment_id}", response_model=AttachmentResponse)
def get_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """Get attachment metadata."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    return attachment


def _get_safe_file_path(attachment: Attachment) -> str:
    """Get full file path with security validation."""
    upload_dir = os.path.abspath(get_upload_dir())
    full_path = os.path.abspath(os.path.join(upload_dir, attachment.storage_path))

    # Security: ensure path is within upload directory
    if not full_path.startswith(upload_dir):
        raise HTTPException(403, "Access denied")

    if not os.path.exists(full_path):
        raise HTTPException(404, "File not found on disk")

    return full_path


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """Download/serve attachment file."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(404, "Attachment not found")

    full_path = _get_safe_file_path(attachment)

    return FileResponse(
        full_path,
        media_type=attachment.mime_type,
        filename=attachment.filename
    )

@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    """Delete attachment if not in use."""
    attachment = db.query(Attachment).filter(Attachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(404, "Attachment not found")

    # Check if in use - BEFORE any deletion
    suite_refs = db.query(SuiteAttachment).filter(SuiteAttachment.attachment_id == attachment_id).count()
    question_refs = db.query(QuestionAttachment).filter(QuestionAttachment.attachment_id == attachment_id).count()

    if suite_refs > 0 or question_refs > 0:
        raise HTTPException(400, f"Attachment in use by {suite_refs} suite(s) and {question_refs} question(s)")

    # Safe deletion order: commit DB first, then delete file
    full_path = os.path.join(get_upload_dir(), attachment.storage_path)
    db.delete(attachment)
    db.commit()

    # Now delete file (after DB commit succeeded)
    if os.path.exists(full_path):
        os.remove(full_path)

    return {"status": "deleted"}
