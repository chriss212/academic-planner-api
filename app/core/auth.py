from __future__ import annotations

import base64
import json
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import Header


TEMP_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    decoded = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
    return json.loads(decoded.decode("utf-8"))


def _user_id_from_subject(subject: str | None) -> UUID:
    if not subject:
        return TEMP_USER_ID

    try:
        return UUID(subject)
    except ValueError:
        return uuid5(NAMESPACE_URL, subject)


async def get_current_user_id(authorization: str | None = Header(default=None)) -> UUID:
    if not authorization:
        return TEMP_USER_ID

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return TEMP_USER_ID

    try:
        payload = _decode_jwt_payload(token)
    except Exception:
        return TEMP_USER_ID

    subject = payload.get("sub") if isinstance(payload, dict) else None
    return _user_id_from_subject(subject if isinstance(subject, str) else None)