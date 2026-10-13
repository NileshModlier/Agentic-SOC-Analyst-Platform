"""Mock EDR alerts.

The payload is a single JSON object from a stand-in endpoint product. It is not
a vendor SDK and it does not talk to a real EDR tenant.
"""

from __future__ import annotations

from soc_platform.domain.canonical import (
    DETECTION_FINDING,
    NETWORK_ACTIVITY,
    PROCESS_ACTIVITY,
    DeviceEntity,
    EndpointEntity,
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
    clip,
    load_json_object,
    map_severity,
    parse_timestamp,
    text_or_none,
)
from soc_platform.ingestion.types import AlertDraft, ParsedIngest

_HASH_IDS = {"md5": 1, "sha1": 2, "sha-1": 2, "sha256": 3, "sha-256": 3}


class MockEdrParser:
    source_kind = SourceKind.MOCK_EDR_ALERT

    def parse(self, payload: bytes) -> ParsedIngest:
        data = load_json_object(payload)
        external_id = clean_external_id(text_or_none(data.get("alert_id")))
        if external_id is None:
            raise IngestParseError("mock EDR alert is missing alert_id", "schema_mismatch")
        title = text_or_none(data.get("title"))
        if title is None:
            raise IngestParseError("mock EDR alert is missing a title", "schema_mismatch")
        severity = map_severity(text_or_none(data.get("severity")))
        detected_raw = data.get("detected_at") or data.get("timestamp")
        if not isinstance(detected_raw, str):
            raise IngestParseError("mock EDR alert is missing detected_at", "missing_timestamp")
        detected_at = parse_timestamp(detected_raw, field="detected_at")
        vendor = text_or_none(data.get("vendor")) or "mock-edr"
        product = text_or_none(data.get("product")) or "MockEDR"
        techniques = _string_list(data.get("technique_ids"))
        tactics = _string_list(data.get("tactics"))
        if not tactics and text_or_none(data.get("tactic")):
            tactics = [text_or_none(data.get("tactic")) or ""]
            tactics = [item for item in tactics if item]
        device = _device(data.get("device"))
        user = _user(data.get("user"))
        process = _process(data.get("process"))
        src_endpoint, dst_endpoint, network_only = _network(data.get("network"))
        event_class = PROCESS_ACTIVITY if process is not None else NETWORK_ACTIVITY if network_only else DETECTION_FINDING
        if event_class is PROCESS_ACTIVITY:
            activity_id, activity_name = 1, "Launch"
        elif event_class is NETWORK_ACTIVITY:
            activity_id, activity_name = 1, "Open"
        else:
            activity_id, activity_name = 1, "Create"
        message = _message(title, process, device, user)
        event = build_event(
            event_class=event_class,
            activity_id=activity_id,
            activity_name=activity_name,
            severity=severity,
            status="success",
            event_time=detected_at,
            message=message,
            source_kind=SourceKind.MOCK_EDR_ALERT.value,
            product_name=product,
            product_vendor=vendor,
            feature_name=title,
            feature_uid=external_id,
            user=user,
            device=device,
            process=process,
            src_endpoint=src_endpoint,
            dst_endpoint=dst_endpoint,
            technique_ids=techniques,
            tactics=tactics,
            unmapped={"alert_id": external_id},
            original_time=detected_raw.strip(),
        )
        host = device.hostname if device is not None else None
        process_token = None
        if process is not None and process.hashes:
            process_token = process.hashes[0].value
        elif process is not None:
            process_token = process.name
        technique_token = techniques[0] if techniques else title
        correlation = clip(f"edr:{technique_token}:{host or '-'}:{process_token or '-'}", 512)
        alert = AlertDraft(
            external_id=external_id,
            title=title,
            description=text_or_none(data.get("description")),
            severity=severity,
            detected_at=detected_at,
            rule_id=external_id,
            rule_name=title,
            technique_ids=tuple(techniques),
            tactics=tuple(tactics),
            vendor=vendor,
            product=product,
            correlation_key=correlation,
        )
        return ParsedIngest(external_id=external_id, event=event, alert=alert)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    found: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = text_or_none(item)
        if text is None or text in seen:
            continue
        seen.add(text)
        found.append(text)
    return found


def _device(value: object) -> DeviceEntity | None:
    if not isinstance(value, dict):
        return None
    device = DeviceEntity(
        uid=text_or_none(value.get("id") or value.get("uid")),
        hostname=text_or_none(value.get("hostname")),
        ip=text_or_none(value.get("ip")),
        os_name=text_or_none(value.get("os") or value.get("os_name")),
        domain=text_or_none(value.get("domain")),
    )
    if device.uid is None and device.hostname is None and device.ip is None:
        return None
    return device


def _user(value: object) -> UserEntity | None:
    if isinstance(value, str):
        return UserEntity(name=text_or_none(value))
    if not isinstance(value, dict):
        return None
    user = UserEntity(
        name=text_or_none(value.get("name")),
        domain=text_or_none(value.get("domain")),
        uid=text_or_none(value.get("uid") or value.get("id")),
    )
    if user.name is None and user.uid is None:
        return None
    return user


def _process(value: object) -> ProcessEntity | None:
    if not isinstance(value, dict):
        return None
    hashes: list[Hash] = []
    raw_hash = text_or_none(value.get("sha256") or value.get("hash"))
    if raw_hash is not None:
        hashes.append(Hash(algorithm="SHA-256", algorithm_id=_HASH_IDS["sha256"], value=raw_hash.lower()))
    parent_value = value.get("parent")
    parent = _process(parent_value) if isinstance(parent_value, dict) else None
    pid = value.get("pid")
    pid_int = pid if isinstance(pid, int) and not isinstance(pid, bool) else None
    process = ProcessEntity(
        pid=pid_int,
        name=text_or_none(value.get("name")),
        path=text_or_none(value.get("path")),
        cmd_line=text_or_none(value.get("command_line") or value.get("cmd_line")),
        hashes=hashes,
        parent_process=parent,
    )
    if process.name is None and process.cmd_line is None and process.path is None and process.pid is None:
        return parent
    return process


def _network(value: object) -> tuple[EndpointEntity | None, EndpointEntity | None, bool]:
    if not isinstance(value, dict):
        return None, None, False
    src = EndpointEntity(
        ip=text_or_none(value.get("src_ip") or value.get("source_ip")),
        port=_port(value.get("src_port") or value.get("source_port")),
    )
    dst = EndpointEntity(
        ip=text_or_none(value.get("dst_ip") or value.get("destination_ip")),
        port=_port(value.get("dst_port") or value.get("destination_port")),
        hostname=text_or_none(value.get("dst_hostname")),
    )
    src_present = src.ip is not None or src.port is not None
    dst_present = dst.ip is not None or dst.port is not None or dst.hostname is not None
    return (src if src_present else None, dst if dst_present else None, src_present or dst_present)


def _port(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 65535:
        return value
    return None


def _message(title: str, process: ProcessEntity | None, device: DeviceEntity | None, user: UserEntity | None) -> str:
    host = device.hostname if device is not None and device.hostname else "unknown host"
    account = qualified_user(user)
    if process is not None and (process.name or process.cmd_line):
        launched = process.name or process.path or "process"
        account_text = f" by {account}" if account else ""
        command = f": {process.cmd_line}" if process.cmd_line else ""
        return f"{title}: {launched} on {host}{account_text}{command}"
    return f"{title} on {host}"
