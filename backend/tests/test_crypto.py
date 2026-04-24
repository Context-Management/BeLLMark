import os
import base64
import pytest

os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-for-unit-tests-only"

from app.core.crypto import encrypt_api_key, decrypt_api_key, SALT_SIZE


class TestCrypto:
    def test_encrypt_decrypt_roundtrip(self):
        """Encrypting then decrypting should return original value."""
        original = "sk-ant-api03-test-key-12345"
        encrypted = encrypt_api_key(original)
        assert encrypted is not None
        assert encrypted != original
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == original

    def test_encrypt_none_returns_none(self):
        assert encrypt_api_key(None) is None
        assert encrypt_api_key("") is None

    def test_decrypt_none_returns_none(self):
        assert decrypt_api_key(None) is None
        assert decrypt_api_key("") is None

    def test_encryption_uses_salt_prefixed_format(self):
        """New format should be base64(salt + fernet_token), not raw Fernet tokens.

        Raw Fernet tokens always start with 'gAAAA' (version byte 0x80 + timestamp).
        The salt-prefixed format wraps salt + token in another base64 layer,
        producing a completely different prefix.
        """
        encrypted = encrypt_api_key("sk-test-key")
        assert not encrypted.startswith("gAAAA"), \
            "Should use salt-prefixed format, not raw Fernet tokens"

    def test_different_encryptions_have_unique_salts(self):
        """Each encryption should embed a different random salt."""
        enc1 = encrypt_api_key("sk-test-key-identical")
        enc2 = encrypt_api_key("sk-test-key-identical")
        raw1 = base64.b64decode(enc1)
        raw2 = base64.b64decode(enc2)
        # First SALT_SIZE bytes are the per-key random salt
        assert raw1[:SALT_SIZE] != raw2[:SALT_SIZE], \
            "Each encryption must use a unique random salt"

    def test_both_encryptions_decrypt_correctly(self):
        """Both different ciphertexts should decrypt to the same value."""
        key = "sk-test-key-identical"
        enc1 = encrypt_api_key(key)
        enc2 = encrypt_api_key(key)
        assert decrypt_api_key(enc1) == key
        assert decrypt_api_key(enc2) == key

    def test_decrypt_invalid_data_returns_none(self):
        """Invalid ciphertext should return None, not crash."""
        assert decrypt_api_key("not-valid-base64-data") is None
        assert decrypt_api_key("dGVzdA==") is None  # valid base64 but not valid encrypted data

    def test_decrypt_legacy_format_returns_none(self):
        """Old fixed-salt encrypted data should return None (migration needed)."""
        # Old format was a raw Fernet token (starts with 'gAAAA')
        # New decrypt expects salt prefix, so old tokens fail gracefully
        result = decrypt_api_key("gAAAAABnwQ_fake_legacy_token")
        assert result is None
