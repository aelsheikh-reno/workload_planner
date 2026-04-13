"""WSGI-compatible auth middleware decorators."""

from __future__ import annotations

import functools
import json
from typing import Any, Callable, Dict

from .service import AuthError, AuthService

_auth_service = AuthService()


def _extract_bearer_token(environ: Dict[str, Any]) -> str | None:
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return None


def _json_error(start_response, status_code: int, message: str):
    body = json.dumps({"error": message}).encode("utf-8")
    status = f"{status_code} {'Unauthorized' if status_code == 401 else 'Forbidden'}"
    start_response(status, [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
    ])
    return [body]


def require_auth(handler: Callable) -> Callable:
    """Decorator that requires a valid Bearer JWT token.

    Injects the ``current_user`` dict into the request context via
    ``environ['float.current_user']``.
    """
    @functools.wraps(handler)
    def wrapper(self, environ, start_response, **kwargs):
        token = _extract_bearer_token(environ)
        if not token:
            return _json_error(start_response, 401, "Authentication required.")
        try:
            user = _auth_service.get_user_from_token(token)
            if user is None:
                return _json_error(start_response, 401, "Invalid or expired token.")
        except AuthError as exc:
            return _json_error(start_response, exc.status, str(exc))
        environ["float.current_user"] = user
        return handler(self, environ, start_response, **kwargs)
    return wrapper


def require_role(role: str) -> Callable:
    """Decorator factory that requires a specific role (after require_auth)."""
    def decorator(handler: Callable) -> Callable:
        @functools.wraps(handler)
        def wrapper(self, environ, start_response, **kwargs):
            token = _extract_bearer_token(environ)
            if not token:
                return _json_error(start_response, 401, "Authentication required.")
            try:
                user = _auth_service.get_user_from_token(token)
                if user is None:
                    return _json_error(start_response, 401, "Invalid or expired token.")
            except AuthError as exc:
                return _json_error(start_response, exc.status, str(exc))
            if user.get("role") != role:
                return _json_error(start_response, 403, f"Role '{role}' required.")
            environ["float.current_user"] = user
            return handler(self, environ, start_response, **kwargs)
        return wrapper
    return decorator
