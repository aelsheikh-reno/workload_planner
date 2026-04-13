"""JWT + bcrypt authentication service."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

from services.persistence import get_db_session
from services.persistence.models import User

_SECRET_KEY = os.environ.get("SECRET_KEY", "float-dev-secret-change-in-production")
_ALGORITHM = "HS256"
_TOKEN_EXPIRY_HOURS = 24 * 7  # 7 days for dev convenience


class AuthError(Exception):
    """Raised for authentication failures."""
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.status = status


class AuthService:
    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Verify credentials and return a signed JWT token."""
        with get_db_session() as session:
            user = session.query(User).filter_by(email=email, is_active=True).first()
            if user is None:
                raise AuthError("Invalid email or password.")
            if not bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
                raise AuthError("Invalid email or password.")

            claims = {
                "sub": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "role": user.role,
                "exp": datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRY_HOURS),
                "iat": datetime.now(timezone.utc),
            }
            token = jwt.encode(claims, _SECRET_KEY, algorithm=_ALGORITHM)
            # PyJWT < 2.0 returns bytes; >= 2.0 returns str — normalise to str
            if isinstance(token, bytes):
                token = token.decode("utf-8")
            return {
                "token": token,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                },
            }

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate a JWT token. Returns the claims dict."""
        try:
            claims = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
            return claims
        except jwt.ExpiredSignatureError:
            raise AuthError("Token has expired. Please log in again.")
        except jwt.InvalidTokenError as exc:
            raise AuthError(f"Invalid token: {exc}")

    def get_user_from_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Return user info from a valid token, or None if invalid."""
        try:
            claims = self.verify_token(token)
            return {
                "id": claims["sub"],
                "email": claims["email"],
                "display_name": claims["display_name"],
                "role": claims["role"],
            }
        except AuthError:
            return None
