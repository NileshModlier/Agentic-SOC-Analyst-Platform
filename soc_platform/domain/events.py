"""Outbox event names. Payloads carry identifiers, not raw event bodies."""

from __future__ import annotations

ALERT_INGESTED = "alert.ingested"
SECURITY_EVENT_NORMALIZED = "security_event.normalized"
INGEST_DEAD_LETTERED = "ingest.dead_lettered"
INGEST_REPLAYED = "ingest.replayed"
INGEST_REPLAY_FAILED = "ingest.replay_failed"
