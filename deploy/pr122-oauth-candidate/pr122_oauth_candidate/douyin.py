"""Douyin Open API OAuth foundation.

This module deliberately covers only the read-only account verification path:
OAuth state, authorization URL construction, token lifecycle metadata, token
exchange, token refresh, and user_info canary calls. Video upload/create,
publication, private messaging, comments, likes, follows, and profile mutation
are outside this contract.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


TASK_ID = "DOUYIN_OPEN_API_INTEGRATION_FOUNDATION_V1"

DOUYIN_AUTHORIZE_URL = "https://open.douyin.com/platform/oauth/connect/"
DOUYIN_ACCESS_TOKEN_URL = "https://open.douyin.com/oauth/access_token/"
DOUYIN_REFRESH_TOKEN_URL = "https://open.douyin.com/oauth/refresh_token/"
DOUYIN_USER_INFO_URL = "https://open.douyin.com/oauth/userinfo/"

MINIMUM_READONLY_SCOPES = ("user_info",)
TEST_ACCOUNT_WHITELIST_SCOPE = "trial.whitelist"
OPTIONAL_REFRESH_SCOPE = "renew_refresh_token"
FORBIDDEN_SCOPE_PREFIXES = (
    "video.",
    "im.",
    "comment.",
    "fans.",
    "following.",
)

TOKEN_STATE_VERSION = 1
STATE_TTL_SECONDS = 600


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def fingerprint(value: str) -> str:
    if not value:
        return "MISSING"
    return sha256_hex(value)[:12]


def mask_identifier(value: str | None, *, prefix: int = 4, suffix: int = 4) -> str:
    if not value:
        return "MISSING"
    if len(value) <= prefix + suffix:
        return value[0:1] + "***"
    return f"{value[:prefix]}***{value[-suffix:]}"


def validate_requested_scopes(scopes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    cleaned = tuple(scope.strip() for scope in scopes if scope and scope.strip())
    if not cleaned:
        raise ValueError("DOUYIN_SCOPE_REQUIRED")
    if cleaned == (TEST_ACCOUNT_WHITELIST_SCOPE,):
        return cleaned
    if TEST_ACCOUNT_WHITELIST_SCOPE in cleaned:
        raise ValueError("DOUYIN_TRIAL_WHITELIST_SCOPE_MUST_BE_STANDALONE")
    for scope in cleaned:
        if any(scope.startswith(prefix) for prefix in FORBIDDEN_SCOPE_PREFIXES):
            raise ValueError("DOUYIN_SCOPE_FORBIDDEN_FOR_FOUNDATION")
    if "user_info" not in cleaned:
        raise ValueError("DOUYIN_USER_INFO_SCOPE_REQUIRED")
    return cleaned


def build_authorization_url(
    *,
    client_key: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] | list[str] = MINIMUM_READONLY_SCOPES,
) -> str:
    if not client_key:
        raise ValueError("DOUYIN_CLIENT_KEY_REQUIRED")
    if not redirect_uri.startswith("https://"):
        raise ValueError("DOUYIN_REDIRECT_URI_HTTPS_REQUIRED")
    requested = validate_requested_scopes(scopes)
    query = urllib.parse.urlencode({
        "client_key": client_key,
        "response_type": "code",
        "scope": ",".join(requested),
        "redirect_uri": redirect_uri,
        "state": state,
    })
    return DOUYIN_AUTHORIZE_URL + "?" + query


def _write_json_0600(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True, indent=2)
            handle.write("\n")
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


class DouyinOAuthStateStore:
    """Durable one-time OAuth state repository."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    def _path(self, state: str) -> Path:
        return self.root / (sha256_hex(state) + ".json")

    def create_state(
        self,
        *,
        redirect_uri: str,
        scopes: tuple[str, ...] | list[str],
        client_key_fingerprint: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        created_at = now or utc_now()
        state = secrets.token_urlsafe(32)
        payload = {
            "task_id": TASK_ID,
            "state_hash": sha256_hex(state),
            "redirect_uri": redirect_uri,
            "scopes": list(validate_requested_scopes(scopes)),
            "client_key_fingerprint": client_key_fingerprint,
            "created_at": iso(created_at),
            "expires_at": iso(created_at + timedelta(seconds=STATE_TTL_SECONDS)),
            "consumed_at": None,
        }
        _write_json_0600(self._path(state), payload)
        return {
            "state": state,
            "state_hash": payload["state_hash"],
            "expires_at": payload["expires_at"],
            "scopes": payload["scopes"],
            "redirect_uri": redirect_uri,
        }

    def consume_state(self, state: str, *, now: datetime | None = None) -> dict[str, Any]:
        current = now or utc_now()
        path = self._path(state)
        if not path.exists():
            return {"status": "REJECTED", "sanitized_error_code": "STATE_NOT_FOUND"}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("consumed_at"):
            return {"status": "REJECTED", "sanitized_error_code": "STATE_ALREADY_CONSUMED"}
        expires_at = datetime.fromisoformat(payload["expires_at"])
        if current >= expires_at:
            return {"status": "REJECTED", "sanitized_error_code": "STATE_EXPIRED"}
        payload["consumed_at"] = iso(current)
        _write_json_0600(path, payload)
        return {"status": "PASS", "state": payload}


@dataclass(frozen=True)
class DouyinTokenLifecycle:
    open_id_masked: str
    union_id_masked: str
    client_key_fingerprint: str
    granted_scopes: tuple[str, ...]
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None
    last_refresh_at: datetime | None
    refresh_attempt_count: int
    reauthorization_required: bool
    revoked: bool

    def as_public_dict(self) -> dict[str, Any]:
        return {
            "token_state_version": TOKEN_STATE_VERSION,
            "open_id_masked": self.open_id_masked,
            "union_id_masked": self.union_id_masked,
            "client_key_fingerprint": self.client_key_fingerprint,
            "granted_scopes": list(self.granted_scopes),
            "access_token_expires_at": iso(self.access_token_expires_at),
            "refresh_token_expires_at": iso(self.refresh_token_expires_at),
            "last_refresh_at": iso(self.last_refresh_at),
            "refresh_attempt_count": self.refresh_attempt_count,
            "reauthorization_required": self.reauthorization_required,
            "revoked": self.revoked,
        }


def parse_token_response(
    payload: dict[str, Any],
    *,
    client_key: str,
    now: datetime | None = None,
    previous_refresh_attempt_count: int = 0,
    refreshed: bool = False,
) -> dict[str, Any]:
    current = now or utc_now()
    data = payload.get("data") or {}
    error_code = str(data.get("error_code", "0"))
    if error_code not in {"0", ""}:
        return {
            "status": "REJECTED",
            "sanitized_error_code": "DOUYIN_TOKEN_RESPONSE_ERROR",
            "provider_error_code": error_code,
            "provider_description": data.get("description") or payload.get("message") or "",
        }
    access_token = data.get("access_token") or ""
    refresh_token = data.get("refresh_token") or ""
    open_id = data.get("open_id") or ""
    union_id = data.get("union_id") or ""
    if not access_token or not refresh_token or not open_id:
        return {"status": "REJECTED", "sanitized_error_code": "DOUYIN_TOKEN_RESPONSE_INCOMPLETE"}
    expires_in = int(data.get("expires_in") or 0)
    refresh_expires_in = int(data.get("refresh_expires_in") or 0)
    scope_text = data.get("scope") or "user_info"
    lifecycle = DouyinTokenLifecycle(
        open_id_masked=mask_identifier(open_id),
        union_id_masked=mask_identifier(union_id),
        client_key_fingerprint=fingerprint(client_key),
        granted_scopes=tuple(scope.strip() for scope in scope_text.split(",") if scope.strip()),
        access_token_expires_at=current + timedelta(seconds=expires_in),
        refresh_token_expires_at=current + timedelta(seconds=refresh_expires_in) if refresh_expires_in else None,
        last_refresh_at=current if refreshed else None,
        refresh_attempt_count=previous_refresh_attempt_count + (1 if refreshed else 0),
        reauthorization_required=False,
        revoked=False,
    )
    return {
        "status": "PASS",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "open_id": open_id,
        "union_id": union_id,
        "lifecycle": lifecycle,
    }


class DouyinTokenLifecycleStore:
    """Stores token metadata only; token values live in OperationsSecretRefStore."""

    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    @property
    def state_path(self) -> Path:
        return self.root / "douyin_token_lifecycle.json"

    def save(self, lifecycle: DouyinTokenLifecycle) -> dict[str, Any]:
        payload = lifecycle.as_public_dict()
        payload["task_id"] = TASK_ID
        payload["secret_value_exposed"] = False
        _write_json_0600(self.state_path, payload)
        return {"status": "PASS", "path": str(self.state_path), "state": payload}

    def load_status(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"status": "MISSING", "reauthorization_required": True}
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        return {"status": "PASS", **payload}


class DouyinOpenApiClient:
    def __init__(self, timeout_seconds: float = 10.0):
        self.timeout_seconds = timeout_seconds

    def _post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(data).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def _post_json(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        encoded = json.dumps(data, ensure_ascii=True).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def exchange_access_token(self, *, client_key: str, client_secret: str, code: str) -> dict[str, Any]:
        return self._post_form(
            DOUYIN_ACCESS_TOKEN_URL,
            {
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )

    def refresh_access_token(self, *, client_key: str, refresh_token: str) -> dict[str, Any]:
        return self._post_form(
            DOUYIN_REFRESH_TOKEN_URL,
            {
                "client_key": client_key,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    def user_info(self, *, access_token: str, open_id: str) -> dict[str, Any]:
        return self._post_json(
            DOUYIN_USER_INFO_URL,
            {
                "access_token": access_token,
                "open_id": open_id,
            },
        )


def sanitize_user_info_response(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    err_no = payload.get("err_no", data.get("error_code", 0))
    if str(err_no) not in {"0", ""}:
        return {
            "status": "REJECTED",
            "sanitized_error_code": "USER_INFO_API_FAILED",
            "provider_error_code": str(err_no),
        }
    return {
        "status": "PASS",
        "open_id_masked": mask_identifier(data.get("open_id")),
        "union_id_masked": mask_identifier(data.get("union_id")),
        "nickname": data.get("nickname") or "",
        "avatar_present": bool(data.get("avatar")),
        "client_key_fingerprint": fingerprint(data.get("client_key") or ""),
    }
