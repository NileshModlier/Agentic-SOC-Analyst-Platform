"""Operator entry points for intake and replay. This module does not serve HTTP."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from soc_platform.config import get_settings
from soc_platform.db.session import create_db_engine
from soc_platform.observability import (
    configure_observability,
    instrument_sqlalchemy,
    service_settings,
    shutdown_tracing,
)
from soc_platform.domain.enums import ReceiptStatus, SourceKind
from soc_platform.domain.errors import IngestError, IngestRejected
from soc_platform.ingestion.pipeline import IngestResult, ingest, replay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="soc-ingest", description="Phase 1 intake and replay")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", help="store one payload and project it")
    ingest_parser.add_argument("--tenant", required=True, type=UUID)
    ingest_parser.add_argument("--kind", required=True, choices=[kind.value for kind in SourceKind])
    ingest_parser.add_argument("--file", required=True, type=Path)

    replay_parser = sub.add_parser("replay", help="re-project one stored source record")
    replay_parser.add_argument("--tenant", required=True, type=UUID)
    replay_parser.add_argument("--source-record", required=True, type=UUID)

    args = parser.parse_args(argv)
    settings = service_settings(get_settings(), "soc-ingest")
    configure_observability(settings)
    engine = create_db_engine(settings.database_url)
    instrument_sqlalchemy(engine)
    try:
        with Session(engine) as session:
            with session.begin():
                if args.command == "ingest":
                    result = ingest(
                        session,
                        tenant_id=args.tenant,
                        source_kind=SourceKind(args.kind),
                        payload=args.file.read_bytes(),
                        max_payload_bytes=settings.max_payload_bytes,
                    )
                else:
                    result = replay(session, tenant_id=args.tenant, source_record_id=args.source_record)
    except IngestRejected as exc:
        print(json.dumps({"error": exc.reason_code, "message": str(exc)}), file=sys.stderr)
        return 3
    except IngestError as exc:
        print(json.dumps({"error": getattr(exc, "reason_code", "ingest_error"), "message": str(exc)}), file=sys.stderr)
        return 3
    finally:
        engine.dispose()
        shutdown_tracing()

    print(json.dumps(_result_payload(result), sort_keys=True))
    if result.receipt_status == ReceiptStatus.DEAD_LETTERED and not result.duplicate:
        return 2
    return 0


def _result_payload(result: IngestResult) -> dict[str, object]:
    return {
        "tenant_id": str(result.tenant_id),
        "source_record_id": str(result.source_record_id),
        "source_kind": result.source_kind.value,
        "content_sha256": result.content_sha256,
        "duplicate": result.duplicate,
        "canonical_event_id": _id(result.canonical_event_id),
        "alert_id": _id(result.alert_id),
        "evidence_id": _id(result.evidence_id),
        "dead_letter_id": _id(result.dead_letter_id),
        "outbox_event_id": _id(result.outbox_event_id),
        "receipt_status": result.receipt_status.value,
    }


def _id(value: UUID | None) -> str | None:
    if value is None:
        return None
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
