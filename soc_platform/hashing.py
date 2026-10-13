"""Byte-identity helpers. Intake dedup and custody both use SHA-256 of the raw bytes."""

from __future__ import annotations

import hashlib


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
