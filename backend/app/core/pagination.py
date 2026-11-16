"""Keyset pagination with opaque cursors.

A cursor holds the sort key of the last returned row plus a fingerprint of its scope
(resource, owner and filters). Reusing it with other filters or by another user is a 422.
Tampering cannot leak data: every query is still filtered by owner. Cursors are encoded,
not encrypted; they contain only sort values the client has already seen.
"""

import base64
import hashlib
import json
from typing import Annotated, Any

from fastapi import Query

from app.core.errors import validation_error

DEFAULT_LIMIT = 20
MAX_LIMIT = 100

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT, description="Page size.")]
Cursor = Annotated[
    str | None,
    Query(min_length=1, max_length=512, description="Opaque cursor scoped to owner and filters."),
]


def scope_fingerprint(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16]


def encode_cursor(scope: str, key: list[Any]) -> str:
    raw = json.dumps({"s": scope, "k": key}, separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None, scope: str, size: int) -> list[Any] | None:
    if cursor is None:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        key = data["k"]
        if data["s"] != scope or not isinstance(key, list) or len(key) != size:
            raise ValueError
    except ValueError, KeyError, TypeError:
        raise validation_error("cursor", "Cursor is invalid or belongs to other filters.") from None
    return key
