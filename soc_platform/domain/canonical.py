"""OCSF-aligned canonical event document.

The document is a subset of OCSF 1.5 classification attributes, not a certified
full-schema export. ``type_uid`` is ``class_uid * 100 + activity_id``. The
``soc`` object is platform custody metadata and is not an OCSF attribute.
Activity ids below are the published OCSF values this normalizer relies on.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

OCSF_VERSION = "1.5.0"
NORMALIZER_VERSION = "1"

SEVERITY_IDS = {
    "unknown": 0,
    "informational": 1,
    "low": 2,
    "medium": 3,
    "high": 4,
    "critical": 5,
}

OUTCOME_IDS = {
    "unknown": 0,
    "success": 1,
    "failure": 2,
    "other": 99,
}


class EventClass(BaseModel):
    model_config = ConfigDict(frozen=True)
    category_uid: int
    category_name: str
    class_uid: int
    class_name: str


PROCESS_ACTIVITY = EventClass(
    category_uid=1, category_name="System Activity", class_uid=1007, class_name="Process Activity"
)
FILE_ACTIVITY = EventClass(
    category_uid=1, category_name="System Activity", class_uid=1001, class_name="File System Activity"
)
AUTHENTICATION = EventClass(
    category_uid=3,
    category_name="Identity & Access Management",
    class_uid=3002,
    class_name="Authentication",
)
USER_MANAGEMENT = EventClass(
    category_uid=3,
    category_name="Identity & Access Management",
    class_uid=3007,
    class_name="User Management",
)
GROUP_MANAGEMENT = EventClass(
    category_uid=3,
    category_name="Identity & Access Management",
    class_uid=3006,
    class_name="Group Management",
)
NETWORK_ACTIVITY = EventClass(
    category_uid=4, category_name="Network Activity", class_uid=4001, class_name="Network Activity"
)
APPLICATION_LIFECYCLE = EventClass(
    category_uid=6, category_name="Application Activity", class_uid=6002, class_name="Application Lifecycle"
)
DETECTION_FINDING = EventClass(
    category_uid=2, category_name="Findings", class_uid=2004, class_name="Detection Finding"
)
EVENT_LOG_ACTIVITY = EventClass(
    category_uid=1, category_name="System Activity", class_uid=1008, class_name="Event Log Activity"
)
BASE_EVENT = EventClass(category_uid=0, category_name="Uncategorized", class_uid=0, class_name="Base Event")

# Process Activity: 1 Launch, 2 Terminate. Authentication: 1 Logon, 2 Logoff.
# File System Activity: 1 Create. Network Activity: 1 Open.
# Detection Finding: 1 Create. 0 Unknown. 99 Other.


class Hash(BaseModel):
    model_config = ConfigDict(extra="forbid")
    algorithm: str
    algorithm_id: int | None = None
    value: str


class ProcessEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pid: int | None = None
    name: str | None = None
    path: str | None = None
    cmd_line: str | None = None
    uid: str | None = None
    hashes: list[Hash] = Field(default_factory=list)
    parent_process: ProcessEntity | None = None


class UserEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    domain: str | None = None
    uid: str | None = None


class DeviceEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str | None = None
    ip: str | None = None
    uid: str | None = None
    os_name: str | None = None
    domain: str | None = None


class FileEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None
    name: str | None = None
    hashes: list[Hash] = Field(default_factory=list)


class EndpointEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ip: str | None = None
    port: int | None = None
    hostname: str | None = None


class Observable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    value: str


class TechniqueRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid: str
    name: str | None = None


class TacticRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    uid: str | None = None
    name: str


class Attack(BaseModel):
    model_config = ConfigDict(extra="forbid")
    technique: TechniqueRef | None = None
    tactic: TacticRef | None = None


class Feature(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    uid: str | None = None


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    vendor_name: str | None = None
    feature: Feature | None = None


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str = OCSF_VERSION
    uid: str | None = None
    logged_time: int | None = None
    original_time: str | None = None
    product: Product = Field(default_factory=Product)
    profiles: list[str] = Field(default_factory=list)


class SocExtension(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_record_id: UUID | None = None
    source_kind: str
    normalizer_version: str = NORMALIZER_VERSION
    content_sha256: str | None = None


class CanonicalEventDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    class_uid: int
    class_name: str
    category_uid: int
    category_name: str
    activity_id: int
    activity_name: str
    type_uid: int
    type_name: str
    severity_id: int
    severity: str
    status_id: int
    status: str
    time: int
    message: str
    metadata: Metadata
    soc: SocExtension
    user: UserEntity | None = None
    device: DeviceEntity | None = None
    process: ProcessEntity | None = None
    file: FileEntity | None = None
    src_endpoint: EndpointEntity | None = None
    dst_endpoint: EndpointEntity | None = None
    observables: list[Observable] = Field(default_factory=list)
    attacks: list[Attack] = Field(default_factory=list)
    unmapped: dict[str, Any] = Field(default_factory=dict)


def to_epoch_ms(value: datetime) -> int:
    utc = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    return (delta.days * 86_400 + delta.seconds) * 1000 + delta.microseconds // 1000


def from_epoch_ms(value: int) -> datetime:
    seconds, millis = divmod(value, 1000)
    return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=millis * 1000)


def build_event(
    *,
    event_class: EventClass,
    activity_id: int,
    activity_name: str,
    severity: str,
    status: str,
    event_time: datetime,
    message: str,
    source_kind: str,
    product_name: str | None = None,
    product_vendor: str | None = None,
    feature_name: str | None = None,
    feature_uid: str | None = None,
    user: UserEntity | None = None,
    device: DeviceEntity | None = None,
    process: ProcessEntity | None = None,
    file: FileEntity | None = None,
    src_endpoint: EndpointEntity | None = None,
    dst_endpoint: EndpointEntity | None = None,
    technique_ids: list[str] | None = None,
    tactics: list[str] | None = None,
    unmapped: dict[str, Any] | None = None,
    original_time: str | None = None,
) -> CanonicalEventDocument:
    if severity not in SEVERITY_IDS:
        raise ValueError(f"unknown severity {severity}")
    if status not in OUTCOME_IDS:
        raise ValueError(f"unknown status {status}")
    if event_time.tzinfo is None:
        raise ValueError("event time must be timezone-aware")

    profiles: list[str] = []
    if device is not None or user is not None or process is not None:
        profiles.append("host")
    techniques = _unique(technique_ids or [])
    tactic_names = _unique(tactics or [])
    attacks = [Attack(technique=TechniqueRef(uid=item)) for item in techniques]
    attacks.extend(Attack(tactic=TacticRef(name=item)) for item in tactic_names)
    if attacks:
        profiles.append("security_control")

    document = CanonicalEventDocument(
        class_uid=event_class.class_uid,
        class_name=event_class.class_name,
        category_uid=event_class.category_uid,
        category_name=event_class.category_name,
        activity_id=activity_id,
        activity_name=activity_name,
        type_uid=event_class.class_uid * 100 + activity_id,
        type_name=f"{event_class.class_name}: {activity_name}",
        severity_id=SEVERITY_IDS[severity],
        severity=severity,
        status_id=OUTCOME_IDS[status],
        status=status,
        time=to_epoch_ms(event_time),
        message=message,
        metadata=Metadata(
            original_time=original_time,
            product=Product(
                name=product_name,
                vendor_name=product_vendor,
                feature=Feature(name=feature_name, uid=feature_uid) if feature_name or feature_uid else None,
            ),
            profiles=profiles,
        ),
        soc=SocExtension(source_kind=source_kind),
        user=user,
        device=device,
        process=process,
        file=file,
        src_endpoint=src_endpoint,
        dst_endpoint=dst_endpoint,
        attacks=attacks,
        unmapped=dict(unmapped or {}),
    )
    document.observables = _observables(document)
    return document


def qualified_user(user: UserEntity | None) -> str | None:
    if user is None or not user.name or user.name in {"-", "(none)"}:
        return None
    if user.domain and user.domain not in {"-", "(none)"}:
        return f"{user.domain}\\{user.name}"
    return user.name


def _observables(document: CanonicalEventDocument) -> list[Observable]:
    found: list[Observable] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str | None) -> None:
        if value is None:
            return
        cleaned = value.strip()
        if cleaned in {"", "-", "null", "None"}:
            return
        key = (kind, cleaned)
        if key in seen:
            return
        seen.add(key)
        found.append(Observable(type=kind, value=cleaned))

    user_name = qualified_user(document.user)
    add("user", user_name)
    if document.device is not None:
        add("hostname", document.device.hostname)
        add("ip", document.device.ip)
        add("domain", document.device.domain)
    if document.src_endpoint is not None:
        add("ip", document.src_endpoint.ip)
        if document.src_endpoint.port is not None:
            add("port", str(document.src_endpoint.port))
    if document.dst_endpoint is not None:
        add("ip", document.dst_endpoint.ip)
        if document.dst_endpoint.port is not None:
            add("port", str(document.dst_endpoint.port))
    if document.process is not None:
        add("process_name", document.process.name)
        for item in document.process.hashes:
            add("hash", item.value.lower())
        parent = document.process.parent_process
        if parent is not None:
            add("process_name", parent.name)
    if document.file is not None:
        add("file_path", document.file.path)
        for item in document.file.hashes:
            add("hash", item.value.lower())
    return found


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered
