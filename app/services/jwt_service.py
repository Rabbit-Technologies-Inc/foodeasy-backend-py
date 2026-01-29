# app/services/jwt_service.py

"""
Backend JWT service: create and verify access tokens with infinite (far-future) expiry.
Uses JWT_SECRET_KEY from environment for signing.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import jwt
from dotenv import load_dotenv

load_dotenv()

# Secret for signing JWTs. Must be set in .env (e.g. a long random string).
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"

# Infinite expiry: 10 years from now (effectively never expire for app usage).
# JWT spec recommends including exp; we use far-future instead of omitting.
JWT_EXPIRY_DAYS = 365 * 10


def _get_secret() -> str:
    if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 16:
        raise ValueError(
            "JWT_SECRET_KEY not configured or too short. "
            "Set JWT_SECRET_KEY in your .env (min 16 characters, random string)."
        )
    return JWT_SECRET_KEY


def create_access_token(user_id: str, phone_number: str) -> str:
    """
    Create a backend JWT access token with infinite (far-future) expiry.
    Payload: sub=user_id, phone_number, iat, exp.
    """
    now = datetime.utcnow()
    exp = now + timedelta(days=JWT_EXPIRY_DAYS)
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "phone_number": phone_number,
        "iat": now,
        "exp": exp,
    }
    return jwt.encode(
        payload,
        _get_secret(),
        algorithm=JWT_ALGORITHM,
    )


def verify_access_token(token: str) -> Dict[str, Any]:
    """
    Verify the backend JWT and return the payload (sub=user_id, phone_number, etc.).
    Raises jwt.InvalidTokenError (or subclass) if invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            _get_secret(),
            algorithms=[JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise
    except jwt.InvalidTokenError:
        raise
