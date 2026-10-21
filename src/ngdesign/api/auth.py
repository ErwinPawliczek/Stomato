"""Bearer-token auth (spec P3-01).

``STOMATO_API_TOKENS`` is a comma-separated list of ``token:owner`` pairs; when
set, every ``/api`` route except ``/api/health`` requires
``Authorization: Bearer <token>`` and the token maps the request to an ``owner``
(projects list only the owner's). Unset means open (local dev) — logged once.
Tokens come from the environment only and are never logged: log lines carry
counts, never values.

The parsed config is cached per process (read once at startup via the lifespan,
lazily on first request otherwise); :func:`reset_auth_cache` is the test seam.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

from fastapi import HTTPException, Request

logger = logging.getLogger("ngdesign.api")

TOKENS_ENV = "STOMATO_API_TOKENS"

#: Every request owns projects under this owner when no token is configured
#: (open mode) — one code path for owner scoping, on and off.
ANONYMOUS_OWNER = "local"


@dataclass(frozen=True)
class AuthState:
    """Parsed auth configuration; ``tokens is None`` means open (no auth)."""

    tokens: dict[str, str] | None


_state: AuthState | None = None
_lock = threading.Lock()


def parse_tokens(raw: str) -> dict[str, str]:
    """Parse ``token:owner`` pairs; a malformed entry is a config error naming
    only the entry's position — never its value."""
    tokens: dict[str, str] = {}
    for position, entry in enumerate(raw.split(","), start=1):
        token, separator, owner = entry.strip().partition(":")
        if not token or not separator or not owner.strip():
            raise ValueError(
                f"{TOKENS_ENV} entry {position} must be a 'token:owner' pair "
                "(the malformed value is not echoed back)"
            )
        tokens[token] = owner.strip()
    return tokens


def auth_state() -> AuthState:
    """The parsed auth config, cached per process; logs the mode once."""
    global _state
    if _state is None:
        with _lock:
            if _state is None:
                raw = os.environ.get(TOKENS_ENV)
                if raw is None:
                    logger.info(
                        "auth: open — %s unset, every /api route accepts unauthenticated local requests",
                        TOKENS_ENV,
                    )
                    _state = AuthState(tokens=None)
                else:
                    tokens = parse_tokens(raw)
                    logger.info("auth: %d bearer token(s) configured via %s", len(tokens), TOKENS_ENV)
                    _state = AuthState(tokens=tokens)
    return _state


def reset_auth_cache() -> None:
    """Drop the cached config (tests re-read the environment)."""
    global _state
    with _lock:
        _state = None


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def current_owner(request: Request) -> str:
    """The owner this request acts as; 401 when auth is on and the token is
    missing or unknown. ``/api/health`` is the liveness probe: always open."""
    if request.url.path == "/api/health":
        return ANONYMOUS_OWNER
    state = auth_state()
    if state.tokens is None:
        return ANONYMOUS_OWNER
    header = request.headers.get("Authorization")
    if header is None:
        raise _unauthorized("Authorization: Bearer <token> required")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Authorization header must be 'Bearer <token>'")
    owner = state.tokens.get(token.strip())
    if owner is None:
        raise _unauthorized("unknown token")
    return owner
