"""TikTok Login Kit OAuth foundation.

This module covers only the Sandbox/Login Kit read-only account connection
path: OAuth state, authorization URL construction, token lifecycle metadata,
token exchange, secure token metadata, and user.info.basic canary calls.
Content Posting API, uploads, direct posts, comments, messages, and account
control are outside this contract.
"""

from __future__ import annotations

from .storage import Database, private_directory

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


TASK_ID = "TIKTOK_SANDBOX_LOGIN_KIT_DEMO_V1"

TIKTOK_AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_ACCESS_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"

MINIMUM_READONLY_SCOPES = ("user.info.basic",)
FORBIDDEN_SCOPES = {
    "video.upload",
    "video.publish",
    "video.list",
    "comment.write",
    "message.write",
    "user.info.stats",
}

TOKEN_STATE_VERSION = 1
STATE_TTL_SECONDS = 600
USER_INFO_BASIC_FIELDS = ("open_id", "union_id", "avatar_url", "display_name")


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
        raise ValueError("TIKTOK_SCOPE_REQUIRED")
    if any(scope in FORBIDDEN_SCOPES for scope in cleaned):
        raise ValueError("TIKTOK_SCOPE_FORBIDDEN_FOR_LOGIN_KIT_DEMO")
    if cleaned != MINIMUM_READONLY_SCOPES:
        raise ValueError("TIKTOK_USER_INFO_BASIC_SCOPE_REQUIRED")
    return cleaned


def build_authorization_url(
    *,
    client_key: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] | list[str] = MINIMUM_READONLY_SCOPES,
    include_scope_parameter: bool = True,
) -> str:
    if not client_key:
        raise ValueError("TIKTOK_CLIENT_KEY_REQUIRED")
    if not redirect_uri.startswith("https://"):
        raise ValueError("TIKTOK_REDIRECT_URI_HTTPS_REQUIRED")
    requested = validate_requested_scopes(scopes)
    params = {
        "client_key": client_key,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    if include_scope_parameter:
        params["scope"] = ",".join(requested)
    query = urllib.parse.urlencode(params)
    return TIKTOK_AUTHORIZE_URL + "?" + query




class TikTokOAuthStateStore:
    """Durable one-time OAuth state repository."""

    def __init__(self, root: Path | str):
        self.root = private_directory(root)
        self.database = Database(self.root)

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
        self.database.put('state:' + sha256_hex(state), payload)
        return {
            "state": state,
            "state_hash": payload["state_hash"],
            "expires_at": payload["expires_at"],
            "scopes": payload["scopes"],
            "redirect_uri": redirect_uri,
        }

    def consume_state(self, state: str, *, now: datetime | None = None) -> dict[str, Any]:
        with self.database.transaction():
            current = now or utc_now()
            key = 'state:' + sha256_hex(state)
            payload = self.database.get(key)
            if payload is None:
                return {'status': 'REJECTED', 'sanitized_error_code': 'STATE_NOT_FOUND'}
            if payload.get('consumed_at'):
                return {'status': 'REJECTED', 'sanitized_error_code': 'STATE_ALREADY_CONSUMED'}
            if current >= datetime.fromisoformat(payload['expires_at']):
                return {'status': 'REJECTED', 'sanitized_error_code': 'STATE_EXPIRED'}
            payload['consumed_at'] = iso(current)
            self.database.put(key, payload)
        return {'status': 'PASS', 'state': payload}


@dataclass(frozen=True)
class TikTokTokenLifecycle:
    open_id_masked: str
    union_id_masked: str
    client_key_fingerprint: str
    granted_scopes: tuple[str, ...]
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime | None
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
            "reauthorization_required": self.reauthorization_required,
            "revoked": self.revoked,
        }


def parse_token_response(
    payload: dict[str, Any],
    *,
    client_key: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or utc_now()
    if payload.get("error"):
        return {
            "status": "REJECTED",
            "sanitized_error_code": "TIKTOK_TOKEN_RESPONSE_ERROR",
            "provider_error": payload.get("error", ""),
        }
    access_token = payload.get("access_token") or ""
    refresh_token = payload.get("refresh_token") or ""
    open_id = payload.get("open_id") or ""
    scope_text = payload.get("scope") or "user.info.basic"
    if not access_token or not refresh_token or not open_id:
        return {"status": "REJECTED", "sanitized_error_code": "TIKTOK_TOKEN_RESPONSE_INCOMPLETE"}
    expires_in = int(payload.get("expires_in") or 0)
    refresh_expires_in = int(payload.get("refresh_expires_in") or 0)
    lifecycle = TikTokTokenLifecycle(
        open_id_masked=mask_identifier(open_id),
        union_id_masked="MISSING",
        client_key_fingerprint=fingerprint(client_key),
        granted_scopes=tuple(scope.strip() for scope in scope_text.split(",") if scope.strip()),
        access_token_expires_at=current + timedelta(seconds=expires_in),
        refresh_token_expires_at=current + timedelta(seconds=refresh_expires_in) if refresh_expires_in else None,
        reauthorization_required=False,
        revoked=False,
    )
    return {
        "status": "PASS",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "open_id": open_id,
        "lifecycle": lifecycle,
    }




class TikTokOpenApiClient:
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

    def _get_json(self, url: str, access_token: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"Authorization": "Bearer " + access_token},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        return json.loads(body)

    def exchange_access_token(
        self,
        *,
        client_key: str,
        client_secret: str,
        code: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        return self._post_form(
            TIKTOK_ACCESS_TOKEN_URL,
            {
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )

    def user_info(self, *, access_token: str) -> dict[str, Any]:
        fields = ",".join(USER_INFO_BASIC_FIELDS)
        return self._get_json(TIKTOK_USER_INFO_URL + "?fields=" + urllib.parse.quote(fields), access_token)


def sanitize_user_info_response(payload: dict[str, Any]) -> dict[str, Any]:
    error = payload.get("error") or {}
    error_code = str(error.get("code", "")).lower() if isinstance(error, dict) else ""
    if error and error_code not in {"ok", ""}:
        return {
            "status": "REJECTED",
            "sanitized_error_code": "USER_INFO_API_FAILED",
            "provider_error_code": str(error.get("code", "")),
        }
    data = payload.get("data") or {}
    user = data.get("user") or data
    return {
        "status": "PASS",
        "open_id_masked": mask_identifier(user.get("open_id")),
        "union_id_masked": mask_identifier(user.get("union_id")),
        "display_name": user.get("display_name") or "",
        "avatar_present": bool(user.get("avatar_url")),
    }
