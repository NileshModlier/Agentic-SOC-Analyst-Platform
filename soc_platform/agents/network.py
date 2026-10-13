"""Investigation tools stay on the local database."""

from __future__ import annotations

_SCHEMES = ("http://", "https://", "ftp://")
_NETWORK_KEYS = frozenset({"url", "uri", "href", "endpoint"})


class NetworkDenied(Exception):
    """A workflow step asked for a network location."""


def assert_local_text(value: str | None) -> None:
    if value is None:
        return
    if value.strip().lower().startswith(_SCHEMES):
        raise NetworkDenied("investigation tools cannot fetch a URL")


def assert_local_arguments(arguments: dict) -> None:
    for key, value in arguments.items():
        if str(key).casefold() in _NETWORK_KEYS:
            raise NetworkDenied("investigation tools cannot receive a network location")
        if isinstance(value, str):
            assert_local_text(value)
