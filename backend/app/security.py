"""
Password hashing (PBKDF2-HMAC with random salt) and JWT issuing/verification.
No third-party auth libraries required beyond PyJWT, to keep the stack light.
"""
import base64
import hashlib
import hmac
import os
import time
from typing import Optional

import jwt

from . import config

PBKDF2_ITERATIONS = 260_000
PBKDF2_ALGO = "sha256"


def hash_password(plain_password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, plain_password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(plain_password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_s, salt_b64, hash_b64 = stored_hash.split("$")
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, AttributeError):
        return False
    derived = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, plain_password.encode("utf-8"), salt, iterations
    )
    return hmac.compare_digest(derived, expected)


def create_access_token(user_id: int, username: str, role: str) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + config.JWT_EXPIRE_MINUTES * 60,
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
