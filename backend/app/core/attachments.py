"""Attachment handling utilities for multimodal message building."""
import base64
import os
from typing import List, Dict, Any, Optional

# Import upload dir config from attachments API
from app.api.attachments import get_upload_dir

def load_attachment_content(storage_path: str) -> bytes:
    """Load attachment content from disk with security validation."""
    upload_dir = os.path.abspath(get_upload_dir())
    full_path = os.path.abspath(os.path.join(upload_dir, storage_path))

    # Security: ensure path is within upload directory (defense in depth)
    if not full_path.startswith(upload_dir + os.sep) and full_path != upload_dir:
        raise ValueError(f"Invalid attachment path: {storage_path}")

    try:
        with open(full_path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        raise ValueError(f"Attachment file not found: {storage_path}")
    except PermissionError:
        raise ValueError(f"Permission denied accessing attachment: {storage_path}")
    except Exception as e:
        raise ValueError(f"Failed to read attachment {storage_path}: {str(e)}")

def estimate_text_tokens(text: str) -> int:
    """Estimate token count for text (~4 chars per token)."""
    return len(text) // 4

def estimate_image_tokens(mime_type: str, size_bytes: int) -> int:
    """Estimate token count for images (conservative fixed estimate).

    Based on typical vision API token usage:
    - Small images (<100KB): ~85 tokens (e.g., icons, thumbnails)
    - Medium images (100-500KB): ~500 tokens (e.g., screenshots)
    - Large images (>500KB): ~1500 tokens (e.g., high-res photos)
    """
    if size_bytes < 100_000:  # < 100KB
        return 85
    elif size_bytes < 500_000:  # < 500KB
        return 500
    else:
        return 1500

def can_send_images(provider: str, supports_vision_flag: Optional[bool] = None) -> bool:
    """Check if provider/model supports vision.

    Args:
        provider: Provider name (e.g., "openai", "anthropic")
        supports_vision_flag: Explicit flag from model preset. Can be bool or int
            from SQLite (1=yes, 0=no, None=unknown). None falls back to provider default.

    Returns:
        True if model supports vision
    """
    # SQLite stores as Integer (0/1/NULL). Convert: 0 → False, 1 → True, None → None
    if supports_vision_flag is not None:
        return bool(supports_vision_flag)

    # No explicit flag — fall back to provider defaults
    # Most major providers support vision on their modern models
    VISION_CAPABLE_PROVIDERS = {
        "openai", "anthropic", "google", "lmstudio",
        "mistral", "deepseek", "grok", "glm", "kimi",
        "openrouter", "ollama"
    }
    return provider.lower() in VISION_CAPABLE_PROVIDERS

def build_multimodal_content(
    text: str,
    attachments: List[Dict[str, Any]],  # [{storage_path, mime_type, filename}]
    provider: str,
    supports_vision: Optional[bool] = None
) -> tuple[Any, int]:
    """Build multimodal message content for LLM API.

    Args:
        text: The text prompt
        attachments: List of attachment dicts
        provider: Provider name for format selection
        supports_vision: Explicit vision support flag

    Returns:
        Tuple of (content, estimated_tokens)
    """
    estimated_tokens = estimate_text_tokens(text)

    if not attachments:
        return text, estimated_tokens

    vision_enabled = can_send_images(provider, supports_vision)

    # Separate text and image attachments
    text_attachments = []
    image_attachments = []

    for att in attachments:
        if att["mime_type"].startswith("image/"):
            image_attachments.append(att)
        else:
            text_attachments.append(att)

    # Append text attachment content to prompt
    combined_text = text
    for att in text_attachments:
        content = load_attachment_content(att["storage_path"])
        try:
            text_content = content.decode("utf-8")
        except UnicodeDecodeError:
            text_content = content.decode("latin-1")
        combined_text += f"\n\n--- Attached file: {att['filename']} ---\n{text_content}"
        estimated_tokens += estimate_text_tokens(text_content)

    # If no images or vision not supported, return text only
    if not image_attachments or not vision_enabled:
        return combined_text, estimated_tokens

    # Build multimodal content based on provider format
    if provider.lower() == "anthropic":
        return _build_anthropic_content(combined_text, image_attachments, estimated_tokens)
    elif provider.lower() == "google":
        return _build_google_content(combined_text, image_attachments, estimated_tokens)
    else:
        # OpenAI-compatible format (OpenAI, LMStudio, Mistral, DeepSeek, Grok, GLM, Kimi)
        return _build_openai_content(combined_text, image_attachments, estimated_tokens)

def _build_openai_content(text: str, images: List[Dict], base_tokens: int) -> tuple[List, int]:
    """Build OpenAI-compatible multimodal content."""
    content = [{"type": "text", "text": text}]
    tokens = base_tokens

    for img in images:
        img_data = load_attachment_content(img["storage_path"])
        b64 = base64.b64encode(img_data).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{img['mime_type']};base64,{b64}"
            }
        })
        tokens += estimate_image_tokens(img["mime_type"], len(img_data))

    return content, tokens

def _build_anthropic_content(text: str, images: List[Dict], base_tokens: int) -> tuple[List, int]:
    """Build Anthropic multimodal content."""
    content = [{"type": "text", "text": text}]
    tokens = base_tokens

    for img in images:
        img_data = load_attachment_content(img["storage_path"])
        b64 = base64.b64encode(img_data).decode("utf-8")
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": img["mime_type"],
                "data": b64
            }
        })
        tokens += estimate_image_tokens(img["mime_type"], len(img_data))

    return content, tokens

def _build_google_content(text: str, images: List[Dict], base_tokens: int) -> tuple[List, int]:
    """Build Google Gemini multimodal content."""
    content = [{"type": "text", "text": text}]
    tokens = base_tokens

    for img in images:
        img_data = load_attachment_content(img["storage_path"])
        b64 = base64.b64encode(img_data).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": f"data:{img['mime_type']};base64,{b64}"
        })
        tokens += estimate_image_tokens(img["mime_type"], len(img_data))

    return content, tokens
