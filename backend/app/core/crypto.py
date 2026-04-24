# backend/app/core/crypto.py
import os
import base64
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

# Salt size in bytes (128-bit random salt per key)
SALT_SIZE = 16


def _get_secret_key() -> str:
    """Get the master secret key from environment."""
    secret_key = os.getenv("BELLMARK_SECRET_KEY")
    if not secret_key:
        raise ValueError(
            "BELLMARK_SECRET_KEY environment variable must be set. "
            "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        )
    return secret_key


def _derive_fernet(secret_key: str, salt: bytes) -> Fernet:
    """Derive a Fernet instance from secret key and salt."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return Fernet(key)


def encrypt_api_key(api_key: Optional[str]) -> Optional[str]:
    """
    Encrypt an API key with a per-key random salt.

    Format: base64(salt_16_bytes + fernet_ciphertext_bytes)
    """
    if not api_key:
        return None

    secret_key = _get_secret_key()
    salt = os.urandom(SALT_SIZE)
    fernet = _derive_fernet(secret_key, salt)
    ciphertext = fernet.encrypt(api_key.encode())

    # Concatenate salt + ciphertext, then base64 encode
    combined = salt + ciphertext
    return base64.b64encode(combined).decode()


def is_legacy_ciphertext(encrypted: str) -> bool:
    """
    Check if an encrypted string uses the old fixed-salt format.

    Attempts decryption with the legacy fixed salt. If it succeeds,
    the key hasn't been migrated yet.
    """
    secret_key = os.getenv("BELLMARK_SECRET_KEY")
    if not secret_key:
        return False  # Can't check without secret key

    try:
        salt = b"bellmark_salt_v1"
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        fernet = Fernet(key)
        fernet.decrypt(encrypted.encode())
        return True  # Legacy format — decrypted successfully
    except Exception:
        return False  # New format or invalid


def decrypt_api_key(encrypted: Optional[str]) -> Optional[str]:
    """
    Decrypt a stored API key.

    Handles the per-key salt format: base64(salt_16_bytes + fernet_ciphertext_bytes)
    Returns None if decryption fails (wrong key, corrupted data, or legacy format).
    """
    if not encrypted:
        return None

    try:
        secret_key = _get_secret_key()
        combined = base64.b64decode(encrypted.encode())

        if len(combined) <= SALT_SIZE:
            logger.warning("Encrypted data too short — possible legacy format or corruption")
            return None

        salt = combined[:SALT_SIZE]
        ciphertext = combined[SALT_SIZE:]

        fernet = _derive_fernet(secret_key, salt)
        return fernet.decrypt(ciphertext).decode()

    except InvalidToken:
        logger.warning("API key decryption failed — wrong key or legacy format")
        return None
    except ValueError as e:
        logger.error(f"Crypto configuration error: {e}")
        return None
    except Exception as e:
        logger.warning(f"API key decryption failed: {e}")
        return None
