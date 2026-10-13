"""Import every model so metadata and Alembic see the schema."""

from soc_platform.models.agent import (
    AgentMemory,
    AgentRun,
    DraftApproval,
    DraftCitation,
    DraftClaim,
    InvestigationDraft,
)
from soc_platform.models.alert import Alert
from soc_platform.models.canonical_event import CanonicalEvent
from soc_platform.models.case import Case
from soc_platform.models.dead_letter import DeadLetter
from soc_platform.models.evidence import Evidence, EvidenceLink
from soc_platform.models.finding import Finding
from soc_platform.models.investigation import Investigation
from soc_platform.models.links import FindingAlert, InvestigationAlert
from soc_platform.models.outbox import OutboxEvent
from soc_platform.models.search import AlertSearchDocument, EventEntity, EventSearchDocument, SecurityEntity
from soc_platform.models.source_record import IngestReceipt, SourceRecord
from soc_platform.models.tenant import Tenant

__all__ = [
    "AgentMemory",
    "AgentRun",
    "Alert",
    "AlertSearchDocument",
    "CanonicalEvent",
    "Case",
    "DeadLetter",
    "DraftApproval",
    "DraftCitation",
    "DraftClaim",
    "EventEntity",
    "EventSearchDocument",
    "Evidence",
    "EvidenceLink",
    "Finding",
    "FindingAlert",
    "IngestReceipt",
    "Investigation",
    "InvestigationAlert",
    "InvestigationDraft",
    "OutboxEvent",
    "SecurityEntity",
    "SourceRecord",
    "Tenant",
]
