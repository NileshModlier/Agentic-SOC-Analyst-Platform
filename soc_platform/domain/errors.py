"""Intake failures. Parse errors are stored; rejections are not."""

from __future__ import annotations

from uuid import UUID


class IngestError(Exception):
    """Base for expected intake failures."""


class IngestRejected(IngestError):
    """The caller violated the intake contract. No source record is written."""

    def __init__(self, message: str, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class TenantNotFound(IngestRejected):
    def __init__(self, tenant_id: UUID) -> None:
        super().__init__(f"tenant {tenant_id} was not found", "tenant_not_found")
        self.tenant_id = tenant_id


class TenantDisabled(IngestRejected):
    def __init__(self, tenant_id: UUID) -> None:
        super().__init__(f"tenant {tenant_id} is disabled", "tenant_disabled")
        self.tenant_id = tenant_id


class PayloadTooLarge(IngestRejected):
    def __init__(self, size: int, limit: int) -> None:
        super().__init__(f"payload is {size} bytes; limit is {limit}", "payload_too_large")
        self.size = size
        self.limit = limit


class IngestParseError(IngestError):
    """The bytes could not be normalized. The pipeline stores them and dead-letters the attempt."""

    def __init__(self, message: str, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class SourceRecordNotFound(IngestError):
    def __init__(self, tenant_id: UUID, source_record_id: UUID) -> None:
        super().__init__(f"source record {source_record_id} was not found for tenant {tenant_id}")
        self.tenant_id = tenant_id
        self.source_record_id = source_record_id
        self.reason_code = "source_record_not_found"
