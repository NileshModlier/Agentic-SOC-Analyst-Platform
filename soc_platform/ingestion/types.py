"""Normalized intake produced by a source parser. Parsers are pure functions of bytes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from soc_platform.domain.canonical import CanonicalEventDocument


@dataclass(frozen=True)
class AlertDraft:
    external_id: str | None
    title: str
    description: str | None
    severity: str
    detected_at: datetime
    rule_id: str | None
    rule_name: str | None
    technique_ids: tuple[str, ...]
    tactics: tuple[str, ...]
    vendor: str | None
    product: str | None
    correlation_key: str | None


@dataclass(frozen=True)
class ParsedIngest:
    external_id: str | None
    event: CanonicalEventDocument
    alert: AlertDraft | None
