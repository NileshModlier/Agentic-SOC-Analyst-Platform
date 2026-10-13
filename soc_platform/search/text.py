"""Normalize security text for PostgreSQL simple-configuration full text search.

The simple configuration does not stem tokens, and it splits on punctuation.
Hostnames, IP addresses, file paths, and process names are therefore indexed
both as words and as a compacted form so a query for ``10.0.0.8`` or
``powershell.exe`` matches the same token that was stored.
"""

from __future__ import annotations

import re

_WORDS = re.compile(r"[0-9A-Za-z]+")
_SEGMENTS = re.compile(r"[\s\\/]+")
_DOCUMENT_LIMIT = 12_000


def fts_document(*parts: str | None, limit: int = _DOCUMENT_LIMIT) -> str:
    chunks: list[str] = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if not text:
            continue
        chunks.append(text)
        for segment in _SEGMENTS.split(text):
            words = _WORDS.findall(segment)
            if words:
                chunks.append(" ".join(words))
            compact = "".join(words)
            if compact:
                chunks.append(compact)
        whole = "".join(_WORDS.findall(text))
        if whole:
            chunks.append(whole)
    return " ".join(chunks)[:limit]


def prepare_fts_query(value: str) -> str:
    """Turn user text into a websearch_to_tsquery string using the same folding as the index."""
    terms: list[str] = []
    for raw in value.split():
        words = _WORDS.findall(raw)
        if not words:
            continue
        if any(not character.isalnum() for character in raw):
            compact = "".join(words)
            if compact:
                terms.append(compact)
            continue
        terms.extend(words)
    return " ".join(terms)
