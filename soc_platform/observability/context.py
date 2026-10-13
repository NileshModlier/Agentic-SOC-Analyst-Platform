"""Request correlation. The value is local to the current task or thread."""

from __future__ import annotations

import re
from contextvars import ContextVar, Token
from uuid import uuid4

_CORRELATION_ID: ContextVar[str | None] = ContextVar("soc_correlation_id", default=None)
_ACCEPTABLE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def get_correlation_id() -> str | None:
    return _CORRELATION_ID.get()


def set_correlation_id(value: str) -> Token[str | None]:
    return _CORRELATION_ID.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    _CORRELATION_ID.reset(token)


def normalize_correlation_id(incoming: str | None) -> str:
    if incoming and _ACCEPTABLE.fullmatch(incoming):
        return incoming
    return str(uuid4())
