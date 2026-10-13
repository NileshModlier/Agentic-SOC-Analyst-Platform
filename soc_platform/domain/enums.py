"""Closed sets stored on Phase 1 records."""

from __future__ import annotations

import enum


class TenantStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class SourceKind(str, enum.Enum):
    SIGMA_ALERT = "sigma_alert"
    MOCK_EDR_ALERT = "mock_edr_alert"
    WINDOWS_EVENT = "windows_event"


class Severity(str, enum.Enum):
    UNKNOWN = "unknown"
    INFORMATIONAL = "informational"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Outcome(str, enum.Enum):
    UNKNOWN = "unknown"
    SUCCESS = "success"
    FAILURE = "failure"
    OTHER = "other"


class AlertStatus(str, enum.Enum):
    NEW = "new"
    IN_REVIEW = "in_review"
    CLOSED = "closed"
    SUPPRESSED = "suppressed"


class FindingStatus(str, enum.Enum):
    DRAFT = "draft"
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class InvestigationStatus(str, enum.Enum):
    OPEN = "open"
    ACTIVE = "active"
    BLOCKED = "blocked"
    CLOSED = "closed"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    CONTAINED = "contained"
    RECOVERED = "recovered"
    CLOSED = "closed"


class Priority(str, enum.Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class ReceiptStatus(str, enum.Enum):
    PROJECTED = "projected"
    DEAD_LETTERED = "dead_lettered"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    DEAD_LETTERED = "dead_lettered"


class DeadLetterStage(str, enum.Enum):
    PARSE = "parse"
    PUBLISH = "publish"
    REPLAY = "replay"


class EvidenceType(str, enum.Enum):
    RAW_PAYLOAD = "raw_payload"


class EntityType(str, enum.Enum):
    USER = "user"
    HOST = "host"
    PROCESS = "process"
    FILE = "file"
    IP = "ip"


class SearchSort(str, enum.Enum):
    EVENT_TIME = "event_time"
    SEVERITY = "severity"
    CREATED_TIME = "created_time"


class AgentName(str, enum.Enum):
    SUPERVISOR = "supervisor"
    TRIAGE = "triage"
    ENTITY = "entity"
    THREAT = "threat"
    REPORTING = "reporting"


class AgentRunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DraftStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    VALIDATION_FAILED = "validation_failed"


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class CitationKind(str, enum.Enum):
    EVENT = "event"
    ALERT = "alert"
    ENTITY = "entity"
    EVIDENCE = "evidence"


class MemoryKind(str, enum.Enum):
    PLAN = "plan"
    OBSERVATION = "observation"
    CLAIM = "claim"
    FAILURE = "failure"
