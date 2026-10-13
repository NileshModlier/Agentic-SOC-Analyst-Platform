"""People approve drafts. Agent names are not people."""

from __future__ import annotations

from soc_platform.api.errors import ApiError
from soc_platform.domain.enums import AgentName

RESERVED_ACTORS = frozenset(
    {member.value for member in AgentName} | {"agent", "system", "soc_agent", "soc_reader"}
)


def require_human(value: str, *, field: str) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned.casefold() in RESERVED_ACTORS:
        raise ApiError(
            422,
            "validation_error",
            "A person must request or decide this draft.",
            [{"loc": [field], "message": "Agent names cannot act as a person."}],
        )
    return cleaned
