"""Encrypted file storage at rest (PRD §4 Security)."""
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

import config

# Derive key from config secret for encryption at rest
def _get_fernet():
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"tool-availability-lookup", iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(config.SECRET_KEY.encode()))
    return Fernet(key)

def save_encrypted(data: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    f = _get_fernet()
    path.write_bytes(f.encrypt(data))

def load_encrypted(path: Path) -> bytes:
    f = _get_fernet()
    return f.decrypt(path.read_bytes())

def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
