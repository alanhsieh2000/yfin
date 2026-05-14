from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
from typing import Any


USER_KEY_SECRET_ENV = "YFIN_USER_KEY_SECRET"


@dataclass(frozen=True)
class McpUserDataPaths:
    data_root: Path
    user_key: str
    user_root: Path
    watchlist_path: Path
    runs_root: Path
    shared_cache_root: Path


def derive_user_key(sub: str, secret: str, provider: str = "google") -> str:
    if not sub.strip():
        raise ValueError("authenticated Google subject is required")
    if not secret:
        raise ValueError(f"{USER_KEY_SECRET_ENV} is required")

    identity = f"{provider}:{sub}"
    return hmac.new(
        secret.encode("utf-8"),
        identity.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def resolve_mcp_user_data_paths(
    base_dir: Path | str,
    token: object | None,
    secret: str | None = None,
) -> McpUserDataPaths:
    sub = _subject_from_token(token)
    resolved_secret = secret if secret is not None else os.environ.get(USER_KEY_SECRET_ENV)
    if not resolved_secret:
        raise ValueError(f"{USER_KEY_SECRET_ENV} is required")

    root = Path(base_dir).resolve()
    data_root = root / "data"
    user_key = derive_user_key(sub, resolved_secret)
    user_root = data_root / "users" / user_key

    return McpUserDataPaths(
        data_root=data_root,
        user_key=user_key,
        user_root=user_root,
        watchlist_path=user_root / "watchlist.csv",
        runs_root=user_root / "runs",
        shared_cache_root=data_root / "shared",
    )


def _subject_from_token(token: object | None) -> str:
    claims = _claims_from_token(token)
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise ValueError("authenticated Google subject is required")
    return sub.strip()


def _claims_from_token(token: object | None) -> dict[str, Any]:
    if token is None:
        raise ValueError("authenticated Google subject is required")

    claims = getattr(token, "claims", None)
    if not isinstance(claims, dict):
        raise ValueError("authenticated Google subject is required")
    return claims
