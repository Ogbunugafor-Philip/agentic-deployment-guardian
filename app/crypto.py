"""AES-256-GCM encryption-at-rest for sensitive data stored in PostgreSQL.

The master key comes from GUARDIAN_ENC_KEY (.env) and is hashed to a 32-byte
(256-bit) key with SHA-256, so any key string works. Ciphertext layout is
nonce(12) || ciphertext || tag, returned as bytes (stored in a BYTEA column).
"""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_NONCE_BYTES = 12


def _key() -> bytes:
    raw = get_settings().guardian_enc_key
    if not raw:
        raise RuntimeError("GUARDIAN_ENC_KEY is not configured")
    return hashlib.sha256(raw.encode("utf-8")).digest()  # 32 bytes -> AES-256


def encrypt(plaintext: bytes) -> bytes:
    nonce = os.urandom(_NONCE_BYTES)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(blob: bytes) -> bytes:
    blob = bytes(blob)
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None)
