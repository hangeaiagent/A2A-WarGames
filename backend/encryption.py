"""
Fernet symmetric encryption for API key storage.

Uses the ``cryptography`` library to encrypt API keys at rest in the
database.  The encryption key is loaded from the ``ENCRYPTION_KEY``
environment variable.  In local-dev mode (no key set), a deterministic
dev-only key is generated and a warning is logged.

Generate a production key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_fernet: Fernet | None = None

# Deterministic dev-only key derived from a fixed passphrase.
# NEVER use this in production — it is public and provides zero security.
_DEV_PASSPHRASE = b"openclaw-dev-only-do-not-use-in-production"
_DEV_KEY = base64.urlsafe_b64encode(hashlib.sha256(_DEV_PASSPHRASE).digest())


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = os.environ.get("ENCRYPTION_KEY")
        if not key:
            logger.warning(
                "ENCRYPTION_KEY is not set — using a deterministic dev-only key. "
                "DO NOT use this in production!  Generate a real key with: "
                'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )
            key = _DEV_KEY.decode()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def encrypt_api_key(plaintext: str) -> bytes:
    """Encrypt an API key string and return the ciphertext bytes."""
    return _get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_api_key(ciphertext: bytes) -> str:
    """Decrypt ciphertext bytes and return the original API key string."""
    return _get_fernet().decrypt(ciphertext).decode("utf-8")
