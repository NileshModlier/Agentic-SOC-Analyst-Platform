"""Windows Event Log XML, Event JSON, and Winlogbeat JSON."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

from soc_platform.domain.canonical import (
    BASE_EVENT,
    DeviceEntity,
    EndpointEntity,
    FileEntity,
    Hash,
    ProcessEntity,
    UserEntity,
    build_event,
    qualified_user,
)
from soc_platform.domain.enums import SourceKind
from soc_platform.domain.errors import IngestParseError
from soc_platform.ingestion.codec import (
    clean_external_id,
    decode_text,
    load_json_object,
    parse_hash_list,
    parse_port,
    parse_timestamp,
    parse_windows_pid,
    text_or_none,
)
from soc_platform.ingestion.taxonomy import ACTIVITY_RULES, ActivityRule
from soc_platform.ingestion.types import ParsedIngest


@dataclass(frozen=True)
class ExtractedWindowsEvent:
    event_id: int
    provider: str
    channel: str | None
    computer: str | None
    occurred_at_raw: str
    level: int | None
    record_id: str | None
    fields: dict[str, str]


class WindowsEventParser:
    source_kind = SourceKind.WINDOWS_EVENT

    def parse(self, payload: bytes) -> ParsedIngest:
        extracted = extract_windows_event(payload)
        return project_windows_event(extracted)


def extract_windows_event(payload: bytes) -> ExtractedWindowsEvent:
    stripped = payload.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"<") or payload.startswith((b"\xff\xfe", b"\xfe\xff")) and decode_text(payload).lstrip().startswith("<"):
        return _from_xml(payload)
    return _from_json(load_json_object(payload))


def project_windows_event(extracted: ExtractedWindowsEvent) -> ParsedIngest:
    occurred = parse_timestamp(extracted.occurred_at_raw, field="TimeCreated")
    provider_key = "sysmon" if "sysmon" in extracted.provider.lower() else "security"
    rule = ACTIVITY_RULES.get(provider_key, {}).get(extracted.event_id)
    if rule is None and provider_key != "security":
        rule = ACTIVITY_RULES.get("security", {}).get(extracted.event_id)
    if rule is None:
        rule = ActivityRule(BASE_EVENT, 99, f"Event {extracted.event_id}", "unknown", _severity_from_level(extracted.level))

    user = _user(extracted.fields, rule)
    device = DeviceEntity(
        hostname=extracted.computer,
        domain=text_or_none(_field(extracted.fields, "SubjectDomainName", "TargetDomainName")),
        os_name="Windows" if extracted.provider or extracted.channel else None,
    )
    process = _process(extracted.fields, rule)
    file_entity = _file(extracted.fields, rule)
    src_endpoint, dst_endpoint = _endpoints(extracted.fields, rule)
    outcome = rule.outcome
    message = _message(extracted, rule, user, process, src_endpoint)
    external_id = clean_external_id(_external_id(extracted))
    event = build_event(
        event_class=rule.event_class,
        activity_id=rule.activity_id,
        activity_name=rule.activity_name,
        severity=rule.severity,
        status=outcome,
        event_time=occurred,
        message=message,
        source_kind=SourceKind.WINDOWS_EVENT.value,
        product_name=extracted.provider or "Windows",
        product_vendor="Microsoft",
        feature_name=str(extracted.event_id),
        feature_uid=extracted.record_id,
        user=user,
        device=device,
        process=process,
        file=file_entity,
        src_endpoint=src_endpoint,
        dst_endpoint=dst_endpoint,
        unmapped={
            "event_id": extracted.event_id,
            "channel": extracted.channel,
            "provider": extracted.provider,
            "record_id": extracted.record_id,
            "level": extracted.level,
            "fields": extracted.fields,
        },
        original_time=extracted.occurred_at_raw,
    )
    return ParsedIngest(external_id=external_id, event=event, alert=None)


def _from_xml(payload: bytes) -> ExtractedWindowsEvent:
    try:
        root = ET.fromstring(decode_text(payload))
    except ET.ParseError as exc:
        raise IngestParseError("windows event XML is not well formed", "invalid_xml") from exc
    if _local(root.tag) != "Event":
        raise IngestParseError("windows event XML root must be Event", "schema_mismatch")
    system = _child(root, "System")
    if system is None:
        raise IngestParseError("windows event XML is missing System", "schema_mismatch")
    provider_node = _child(system, "Provider")
    provider = ""
    if provider_node is not None:
        provider = provider_node.attrib.get("Name", "")
    event_id = _required_int(_text_of(_child(system, "EventID")), "EventID")
    created = _child(system, "TimeCreated")
    occurred = created.attrib.get("SystemTime") if created is not None else None
    if not occurred:
        raise IngestParseError("missing TimeCreated", "missing_timestamp")
    computer = _text_of(_child(system, "Computer"))
    channel = _text_of(_child(system, "Channel"))
    level = _optional_int(_text_of(_child(system, "Level")))
    record_id = _text_of(_child(system, "EventRecordID"))
    fields = _xml_fields(_child(root, "EventData"))
    return ExtractedWindowsEvent(
        event_id=event_id,
        provider=provider,
        channel=channel,
        computer=computer,
        occurred_at_raw=occurred,
        level=level,
        record_id=record_id,
        fields=fields,
    )


def _from_json(data: dict) -> ExtractedWindowsEvent:
    if isinstance(data.get("winlog"), dict):
        return _from_winlogbeat(data)
    event = data.get("Event") if isinstance(data.get("Event"), dict) else data
    system = event.get("System") if isinstance(event.get("System"), dict) else None
    if system is None:
        raise IngestParseError("windows event JSON is missing System or winlog", "schema_mismatch")
    provider_value = system.get("Provider")
    if isinstance(provider_value, dict):
        provider = text_or_none(provider_value.get("Name") or provider_value.get("@Name")) or ""
    else:
        provider = text_or_none(provider_value) or ""
    event_id = _event_id_value(system.get("EventID"))
    created = system.get("TimeCreated")
    if isinstance(created, dict):
        occurred = text_or_none(created.get("SystemTime") or created.get("@SystemTime"))
    else:
        occurred = text_or_none(created)
    if occurred is None:
        raise IngestParseError("missing TimeCreated", "missing_timestamp")
    return ExtractedWindowsEvent(
        event_id=event_id,
        provider=provider,
        channel=text_or_none(system.get("Channel")),
        computer=text_or_none(system.get("Computer")),
        occurred_at_raw=occurred,
        level=_optional_int(system.get("Level")),
        record_id=text_or_none(system.get("EventRecordID")),
        fields=_json_fields(event.get("EventData")),
    )


def _from_winlogbeat(data: dict) -> ExtractedWindowsEvent:
    winlog = data["winlog"]
    event_node = data.get("event") if isinstance(data.get("event"), dict) else {}
    event_id = _event_id_value(winlog.get("event_id", event_node.get("code")))
    host = data.get("host") if isinstance(data.get("host"), dict) else {}
    occurred = text_or_none(data.get("@timestamp") or winlog.get("time_created"))
    if occurred is None:
        raise IngestParseError("missing TimeCreated", "missing_timestamp")
    raw_fields = winlog.get("event_data") if isinstance(winlog.get("event_data"), dict) else {}
    fields = {str(key): "" if value is None else str(value) for key, value in raw_fields.items()}
    return ExtractedWindowsEvent(
        event_id=event_id,
        provider=text_or_none(winlog.get("provider_name")) or "",
        channel=text_or_none(winlog.get("channel")),
        computer=text_or_none(winlog.get("computer_name") or host.get("hostname") or host.get("name")),
        occurred_at_raw=occurred,
        level=_optional_int(winlog.get("level")),
        record_id=text_or_none(winlog.get("record_id")),
        fields=fields,
    )


def _xml_fields(event_data: ET.Element | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    if event_data is None:
        return fields
    for child in list(event_data):
        if _local(child.tag) != "Data":
            continue
        name = child.attrib.get("Name")
        if not name:
            continue
        fields[name] = (child.text or "").strip()
    return fields


def _json_fields(event_data: object) -> dict[str, str]:
    if isinstance(event_data, dict):
        if "Data" in event_data:
            return _json_fields(event_data["Data"])
        fields: dict[str, str] = {}
        for key, value in event_data.items():
            if key.startswith("@"):
                continue
            rendered = text_or_none(value)
            if rendered is not None:
                fields[str(key)] = rendered
        return fields
    if isinstance(event_data, list):
        fields = {}
        for item in event_data:
            if not isinstance(item, dict):
                continue
            name = text_or_none(item.get("Name") or item.get("@Name"))
            if name is None:
                continue
            rendered = text_or_none(item.get("#text") or item.get("text") or item.get("$"))
            fields[name] = rendered or ""
        return fields
    return {}


def _event_id_value(value: object) -> int:
    if isinstance(value, dict):
        value = value.get("#text", value.get("value", value.get("$")))
    return _required_int(value, "EventID")


def _required_int(value: object, field: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise IngestParseError(f"windows event is missing {field}", "schema_mismatch")


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _severity_from_level(level: int | None) -> str:
    if level == 1:
        return "critical"
    if level == 2:
        return "medium"
    if level == 3:
        return "low"
    return "informational"


def _field(fields: dict[str, str], *names: str) -> str | None:
    folded = {key.lower(): value for key, value in fields.items()}
    for name in names:
        value = text_or_none(fields.get(name))
        if value is None:
            value = text_or_none(folded.get(name.lower()))
        if value is not None:
            return value
    return None


def _user(fields: dict[str, str], rule: ActivityRule) -> UserEntity | None:
    name = _field(fields, "TargetUserName", "SubjectUserName", "User")
    domain = _field(fields, "TargetDomainName", "SubjectDomainName")
    if name is None and domain is None:
        return None
    return UserEntity(name=name, domain=domain)


def _process(fields: dict[str, str], rule: ActivityRule) -> ProcessEntity | None:
    if rule.event_class.class_uid not in {1007, 4001}:
        return None
    path = _field(fields, "NewProcessName", "Image", "ProcessName")
    command = _field(fields, "CommandLine")
    pid = parse_windows_pid(_field(fields, "NewProcessId", "ProcessId"))
    parent_path = _field(fields, "ParentProcessName", "ParentImage")
    parent_command = _field(fields, "ParentCommandLine")
    parent_pid = parse_windows_pid(_field(fields, "ParentProcessId", "ParentPid"))
    if path is None and command is None and pid is None and parent_path is None:
        return None
    parent = None
    if parent_path or parent_command or parent_pid is not None:
        parent = ProcessEntity(
            pid=parent_pid,
            name=_basename(parent_path),
            path=parent_path,
            cmd_line=parent_command,
        )
    hashes = [Hash(algorithm=algorithm, algorithm_id=algorithm_id, value=digest) for algorithm, algorithm_id, digest in parse_hash_list(_field(fields, "Hashes"))]
    return ProcessEntity(
        pid=pid,
        name=_basename(path) or _basename(command),
        path=path,
        cmd_line=command,
        hashes=hashes,
        parent_process=parent,
    )


def _file(fields: dict[str, str], rule: ActivityRule) -> FileEntity | None:
    if rule.event_class.class_uid != 1001:
        return None
    path = _field(fields, "TargetFilename", "FileName")
    if path is None:
        return None
    return FileEntity(path=path, name=_basename(path))


def _endpoints(fields: dict[str, str], rule: ActivityRule) -> tuple[EndpointEntity | None, EndpointEntity | None]:
    src_ip = _field(fields, "IpAddress", "SourceIp", "SourceAddress")
    dst_ip = _field(fields, "DestinationIp", "DestAddress")
    src_port = parse_port(_field(fields, "SourcePort"))
    dst_port = parse_port(_field(fields, "DestinationPort", "DestPort"))
    workstation = _field(fields, "WorkstationName")
    src = None
    dst = None
    if src_ip or src_port is not None or workstation:
        src = EndpointEntity(ip=src_ip, port=src_port, hostname=workstation)
    if dst_ip or dst_port is not None:
        dst = EndpointEntity(ip=dst_ip, port=dst_port)
    if rule.event_class.class_uid == 3002 and src is None and src_ip:
        src = EndpointEntity(ip=src_ip)
    return src, dst


def _message(
    extracted: ExtractedWindowsEvent,
    rule: ActivityRule,
    user: UserEntity | None,
    process: ProcessEntity | None,
    src: EndpointEntity | None,
) -> str:
    account = qualified_user(user) or "unknown user"
    host = extracted.computer or "unknown host"
    if rule.event_class.class_uid == 3002 and rule.activity_name == "Logon":
        logon_type = _field(extracted.fields, "LogonType") or "unknown"
        where = src.ip if src and src.ip else host
        verb = "logged on" if rule.outcome == "success" else "failed to log on"
        return f"User {account} {verb} (logon type {logon_type}) from {where}"
    if rule.event_class.class_uid == 3002 and rule.activity_name == "Logoff":
        return f"User {account} logged off {host}"
    if rule.event_class.class_uid == 1007 and rule.activity_name == "Launch" and process is not None:
        launched = process.path or process.name or "process"
        command = process.cmd_line or ""
        return f"Process {launched} launched by {account}" + (f": {command}" if command else "")
    if rule.event_class.class_uid == 1007 and rule.activity_name == "Terminate" and process is not None:
        return f"Process {process.path or process.name or 'process'} terminated on {host}"
    if rule.event_class.class_uid == 1001 and rule.activity_name == "Create":
        return f"File {_field(extracted.fields, 'TargetFilename') or 'unknown'} created on {host}"
    if rule.event_class.class_uid == 4001:
        destination = _field(extracted.fields, "DestinationIp") or "unknown"
        return f"Network connection from {host} to {destination}"
    if extracted.event_id == 1102:
        return f"Windows event log cleared on {host}"
    return f"Windows event {extracted.event_id} from {extracted.provider or 'unknown provider'} on {host}"


def _external_id(extracted: ExtractedWindowsEvent) -> str | None:
    if extracted.record_id is None:
        return None
    parts = [part for part in (extracted.computer, extracted.channel, extracted.record_id) if part]
    return ":".join(parts)


def _basename(path: str | None) -> str | None:
    if path is None:
        return None
    normalized = path.replace("\\", "/").rstrip("/")
    if not normalized:
        return None
    name = normalized.rsplit("/", 1)[-1]
    return name or None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(parent: ET.Element, name: str) -> ET.Element | None:
    for child in list(parent):
        if _local(child.tag) == name:
            return child
    return None


def _text_of(node: ET.Element | None) -> str | None:
    if node is None or node.text is None:
        return None
    cleaned = node.text.strip()
    return cleaned or None

