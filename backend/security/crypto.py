"""
SmartCCTV SIH26187 — Cryptographic Utilities.

AES-256-GCM file encryption/decryption, PBKDF2 key derivation,
and SHA-256 file/bytes hashing for evidence integrity.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# AES-256-GCM nonce length (96-bit per NIST recommendation)
_NONCE_SIZE = 12
# PBKDF2 iteration count (OWASP 2024 minimum for SHA-256)
_KDF_ITERATIONS = 100_000
# AES-256 key length in bytes
_KEY_SIZE = 32


# ---------------------------------------------------------------------------
# Key Generation
# ---------------------------------------------------------------------------


def generate_file_key() -> bytes:
    """Generate a cryptographically secure random 32-byte AES-256 key.

    Returns:
        32 bytes of CSPRNG output suitable for AES-256-GCM.
    """
    return os.urandom(_KEY_SIZE)


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: Plain-text password or master secret string.
        salt:     16-byte random salt; must be stored alongside ciphertext.

    Returns:
        32-byte derived key.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=salt,
        iterations=_KDF_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(password.encode("utf-8"))


def get_master_key() -> bytes:
    """Derive the application master key from SECRET_KEY path value.

    Uses a fixed salt derived from the key path string.  For production,
    rotate SECRET_KEY and re-encrypt evidence blobs.

    Returns:
        32-byte master encryption key.
    """
    from backend.config import settings

    secret = settings.SECRET_KEY
    # Deterministic salt from the secret_key path — not stored separately,
    # which is intentional for single-master-key derivation.
    salt = hashlib.sha256(secret.encode()).digest()[:16]
    return derive_key(secret, salt)



def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Encrypt raw bytes with AES-256-GCM and return [nonce + ciphertext].

    Args:
        data: Plaintext bytes.
        key:  32-byte AES-256 key.

    Returns:
        Bytes object: [12-byte nonce][ciphertext+tag].
    """
    if len(key) != _KEY_SIZE:
        raise ValueError(f"Key must be {_KEY_SIZE} bytes.")
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    return nonce + aesgcm.encrypt(nonce, data, None)


def decrypt_bytes(data: bytes, key: bytes) -> bytes:
    """Decrypt bytes produced by encrypt_bytes().

    Args:
        data: [nonce + ciphertext + tag] bytes.
        key:  32-byte AES-256 key.

    Returns:
        Decrypted plaintext bytes.
    """
    if len(key) != _KEY_SIZE:
        raise ValueError(f"Key must be {_KEY_SIZE} bytes.")
    nonce = data[:_NONCE_SIZE]
    ciphertext = data[_NONCE_SIZE:]
    return AESGCM(key).decrypt(nonce, ciphertext, None)


# ---------------------------------------------------------------------------
# SHA-256 Hashing
# ---------------------------------------------------------------------------


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA-256 hex digest of a file in 64 KiB chunks.

    Args:
        file_path: Path to file on disk.

    Returns:
        Lower-case hex string of SHA-256 digest.
    """
    digest = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_sha256_bytes(data: bytes) -> str:
    """Compute the SHA-256 hex digest of an in-memory bytes object.

    Args:
        data: Raw bytes to hash.

    Returns:
        Lower-case hex string of SHA-256 digest.
    """
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Convenience wrappers (auto master key)
# ---------------------------------------------------------------------------


def encrypt_file(src_path: Path, dst_path: Path, key: bytes | None = None) -> None:
    """Encrypt src_path -> dst_path using AES-256-GCM.

    When key is None the application master key is used automatically.
    """
    _key = key if key is not None else get_master_key()
    if len(_key) != _KEY_SIZE:
        raise ValueError(f"Key must be {_KEY_SIZE} bytes; got {len(_key)}.")
    if not src_path.exists():
        raise FileNotFoundError(f"Source file not found: {src_path}")
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(_key)
    plaintext = src_path.read_bytes()
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_bytes(nonce + ciphertext)


def decrypt_file_to_bytes(src_path: Path, key: bytes | None = None) -> bytes:
    """Decrypt an AES-256-GCM encrypted file and return the plaintext bytes.

    When key is None the application master key is used automatically.
    This is the primary function used by the evidence API to stream clips.
    """
    _key = key if key is not None else get_master_key()
    raw = src_path.read_bytes()
    if len(raw) < _NONCE_SIZE + 16:
        raise ValueError("Ciphertext too short to contain nonce + GCM tag.")
    nonce = raw[:_NONCE_SIZE]
    ciphertext = raw[_NONCE_SIZE:]
    return AESGCM(_key).decrypt(nonce, ciphertext, None)
