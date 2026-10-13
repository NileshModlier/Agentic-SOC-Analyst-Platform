"""Redis command metrics and spans. The command result is unchanged."""

from __future__ import annotations

import time
from typing import TypeVar

from soc_platform.observability.metrics import record_redis
from soc_platform.observability.tracing import span

_CLIENT = TypeVar("_CLIENT")


def instrument_redis_client(client: _CLIENT) -> _CLIENT:
    if getattr(client, "_soc_redis_wrapped", False):
        return client
    original = client.execute_command  # type: ignore[attr-defined]

    def execute(*args, **kwargs):  # noqa: ANN002, ANN003
        command = _command_name(args)
        started = time.perf_counter()
        try:
            with span("redis.command", **{"db.system": "redis", "db.operation": command}):
                result = original(*args, **kwargs)
        except Exception:
            record_redis(command, time.perf_counter() - started, error=True)
            raise
        record_redis(command, time.perf_counter() - started, error=False)
        return result

    client.execute_command = execute  # type: ignore[attr-defined]
    client._soc_redis_wrapped = True  # type: ignore[attr-defined]
    return client


def _command_name(args: tuple[object, ...]) -> str:
    if not args:
        return "unknown"
    raw = args[0]
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", "replace")
    name = str(raw).split(None, 1)[0].upper()
    if len(name) > 32 or not name.replace("_", "").isalnum():
        return "unknown"
    return name
