from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Optional
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, parse_authentication_credential_json, parse_registration_credential_json
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .auth_context import current_user_id
from .db import AuthSession, User, WebAuthnCredential, session_scope

router = APIRouter(prefix="/api/passkey", tags=["passkeys"])

_challenges: dict[str, bytes] = {}


class UsernameBody(BaseModel):
    username: str = Field(default="settlex-cfo", min_length=2, max_length=80)


class CredentialBody(BaseModel):
    username: str = Field(default="settlex-cfo", min_length=2, max_length=80)
    credential: dict[str, Any]


def _rp_from_request(request: Request) -> tuple[str, str]:
    origin = (
        request.headers.get("origin")
        or os.environ.get("WEBAUTHN_ORIGIN")
        or "http://127.0.0.1:5173"
    ).rstrip("/")
    parsed = urlparse(origin)
    rp_id = os.environ.get("WEBAUTHN_RP_ID") or parsed.hostname or "localhost"
    return rp_id, origin


def _get_or_create_user(username: str) -> User:
    username = username.strip().lower()
    with session_scope() as db:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user:
            db.expunge(user)
            return user
        user = User(id=str(uuid4()), username=username, display_name=username)
        db.add(user)
        db.flush()
        db.expunge(user)
        return user


def issue_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with session_scope() as db:
        db.add(
            AuthSession(
                token=token,
                user_id=user_id,
                expires_at=datetime.utcnow() + timedelta(hours=12),
            )
        )
    return token


def user_from_token(token: Optional[str]) -> Optional[User]:
    if not token:
        return None
    with session_scope() as db:
        row = db.query(AuthSession).filter(AuthSession.token == token).one_or_none()
        if not row or row.expires_at < datetime.utcnow():
            return None
        user = db.query(User).filter(User.id == row.user_id).one_or_none()
        if user:
            db.expunge(user)
        return user


def bearer_token(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def require_passkey_user(request: Request) -> User:
    user = user_from_token(bearer_token(request))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "Passkey login required",
                "error_code": "PASSKEY_REQUIRED",
                "message": "Login with Passkey before triggering AI negotiation agents",
            },
        )
    current_user_id.set(user.id)
    return user


STEP_UP_MAX_AGE = timedelta(seconds=60)


def require_fresh_passkey(request: Request) -> User:
    """Step-up auth for signing a payment: the bearer token must come from a
    WebAuthn assertion (FaceID / TouchID) made moments ago, and works only once."""
    token = bearer_token(request)
    with session_scope() as db:
        row = db.query(AuthSession).filter(AuthSession.token == token).one_or_none() if token else None
        if not row or row.created_at < datetime.utcnow() - STEP_UP_MAX_AGE:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "error": "Biometric confirmation required",
                    "error_code": "PASSKEY_STEP_UP_REQUIRED",
                    "message": "Confirm this approval with your Passkey (FaceID / TouchID)",
                },
            )
        user = db.query(User).filter(User.id == row.user_id).one()
        db.expunge(user)
        db.delete(row)
    current_user_id.set(user.id)
    return user


@router.post("/register/options")
async def register_options(body: UsernameBody, request: Request):
    user = _get_or_create_user(body.username)
    rp_id, _origin = _rp_from_request(request)
    options = generate_registration_options(
        rp_id=rp_id,
        rp_name="Settlex",
        user_id=user.id.encode("utf-8"),
        user_name=user.username,
        user_display_name=user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    _challenges[user.username] = options.challenge
    return {"options": options_to_json(options), "username": user.username}


@router.post("/register/verify")
async def register_verify(body: CredentialBody, request: Request):
    username = body.username.strip().lower()
    challenge = _challenges.get(username)
    if not challenge:
        raise HTTPException(status_code=400, detail={"error_code": "MISSING_CHALLENGE"})
    rp_id, origin = _rp_from_request(request)
    try:
        credential = parse_registration_credential_json(body.credential)
        verification = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "WEBAUTHN_REGISTER_FAILED", "message": str(exc)},
        ) from exc

    user = _get_or_create_user(username)
    cred_id = bytes_to_base64url(verification.credential_id)
    with session_scope() as db:
        existing = db.query(WebAuthnCredential).filter(WebAuthnCredential.id == cred_id).one_or_none()
        if existing:
            existing.public_key = verification.credential_public_key
            existing.sign_count = verification.sign_count
        else:
            db.add(
                WebAuthnCredential(
                    id=cred_id,
                    user_id=user.id,
                    public_key=verification.credential_public_key,
                    sign_count=verification.sign_count,
                    device_type="platform",
                )
            )
    _challenges.pop(username, None)
    token = issue_session(user.id)
    current_user_id.set(user.id)
    return {"ok": True, "token": token, "username": user.username, "user_id": user.id}


@router.post("/login/options")
async def login_options(body: UsernameBody, request: Request):
    username = body.username.strip().lower()
    rp_id, _origin = _rp_from_request(request)
    allow: list[PublicKeyCredentialDescriptor] = []
    with session_scope() as db:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user:
            for cred in db.query(WebAuthnCredential).filter(WebAuthnCredential.user_id == user.id):
                allow.append(PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.id)))
    options = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=allow or None,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    _challenges[f"login:{username}"] = options.challenge
    return {"options": options_to_json(options), "username": username}


@router.post("/login/verify")
async def login_verify(body: CredentialBody, request: Request):
    username = body.username.strip().lower()
    challenge = _challenges.get(f"login:{username}")
    if not challenge:
        raise HTTPException(status_code=400, detail={"error_code": "MISSING_CHALLENGE"})
    rp_id, origin = _rp_from_request(request)

    raw_id = body.credential.get("id") or body.credential.get("rawId")
    if not raw_id:
        raise HTTPException(status_code=400, detail={"error_code": "MISSING_CREDENTIAL_ID"})

    with session_scope() as db:
        cred = db.query(WebAuthnCredential).filter(WebAuthnCredential.id == raw_id).one_or_none()
        if not cred:
            raise HTTPException(status_code=404, detail={"error_code": "UNKNOWN_PASSKEY"})
        public_key = cred.public_key
        sign_count = cred.sign_count
        user_id = cred.user_id

    try:
        credential = parse_authentication_credential_json(body.credential)
        verification = verify_authentication_response(
            credential=credential,
            expected_challenge=challenge,
            expected_rp_id=rp_id,
            expected_origin=origin,
            credential_public_key=public_key,
            credential_current_sign_count=sign_count,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={"error_code": "WEBAUTHN_LOGIN_FAILED", "message": str(exc)},
        ) from exc

    with session_scope() as db:
        cred = db.query(WebAuthnCredential).filter(WebAuthnCredential.id == raw_id).one()
        cred.sign_count = verification.new_sign_count
        user = db.query(User).filter(User.id == user_id).one()
        username_out = user.username

    _challenges.pop(f"login:{username}", None)
    token = issue_session(user_id)
    current_user_id.set(user_id)
    return {"ok": True, "token": token, "username": username_out, "user_id": user_id}


@router.get("/me")
async def me(request: Request):
    user = user_from_token(bearer_token(request))
    if not user:
        return {"authenticated": False}
    return {"authenticated": True, "username": user.username, "user_id": user.id}


@router.post("/logout")
async def logout(request: Request):
    token = bearer_token(request)
    if token:
        with session_scope() as db:
            row = db.query(AuthSession).filter(AuthSession.token == token).one_or_none()
            if row:
                db.delete(row)
    current_user_id.set(None)
    return {"ok": True}
