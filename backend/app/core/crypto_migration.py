"""
One-time migration: re-encrypt all API keys from fixed-salt to per-key-salt format.

Run: cd backend && python -m app.core.crypto_migration

This reads each ModelPreset's encrypted API key, decrypts with the OLD fixed-salt
method, then re-encrypts with the NEW per-key-salt method.

Safe to run multiple times — already-migrated keys will fail old decryption
and be skipped.
"""
import os
import sys
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Must set env before importing app modules
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

from app.db.database import SessionLocal
from app.db.models import ModelPreset
from app.core.crypto import encrypt_api_key


def _decrypt_legacy(encrypted: str) -> str | None:
    """Decrypt using the OLD fixed-salt method."""
    secret_key = os.getenv("BELLMARK_SECRET_KEY")
    if not secret_key:
        return None
    try:
        salt = b"bellmark_salt_v1"
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        fernet = Fernet(key)
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return None


def migrate():
    db = SessionLocal()
    try:
        presets = db.query(ModelPreset).filter(ModelPreset.api_key_encrypted.isnot(None)).all()
        migrated = 0
        skipped = 0

        for preset in presets:
            # Try legacy decryption
            plaintext = _decrypt_legacy(preset.api_key_encrypted)
            if plaintext:
                # Re-encrypt with new per-key salt
                preset.api_key_encrypted = encrypt_api_key(plaintext)
                migrated += 1
            else:
                # Already migrated or corrupted
                skipped += 1

        db.commit()
        print(f"Migration complete: {migrated} re-encrypted, {skipped} skipped")
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
