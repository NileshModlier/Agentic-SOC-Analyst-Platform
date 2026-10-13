"""Parser tests. These do not need PostgreSQL."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from soc_platform.domain.canonical import CanonicalEventDocument
from soc_platform.domain.errors import IngestParseError
from soc_platform.ingestion.mock_edr import MockEdrParser
from soc_platform.ingestion.sigma import SigmaAlertParser
from soc_platform.ingestion.windows_event import WindowsEventParser

SIGMA = {
    "alert_id": "alert-1",
    "detected_at": "2026-10-06T12:00:01Z",
    "rule": {
        "id": "5f6a0c8e-1234-5678-9abc-def012345678",
        "title": "Suspicious Encoded PowerShell",
        "level": "high",
        "description": "Encoded powershell",
        "tags": ["attack.execution", "attack.t1059.001"],
        "logsource": {"product": "windows", "category": "process_creation"},
    },
    "event": {
        "@timestamp": "2026-10-06T12:00:00.000Z",
        "host": {"hostname": "WKSTN-01"},
        "winlog": {
            "channel": "Microsoft-Windows-Sysmon/Operational",
            "provider_name": "Microsoft-Windows-Sysmon",
            "event_id": 1,
            "computer_name": "WKSTN-01.corp.local",
            "record_id": 100,
            "event_data": {
                "Image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                "CommandLine": "powershell.exe -enc AA==",
                "User": "alice",
                "ProcessId": "4321",
                "ParentImage": r"C:\Windows\explorer.exe",
                "Hashes": "SHA256=ABC123",
            },
        },
    },
}

EDR = {
    "vendor": "mock-edr",
    "product": "MockEDR",
    "alert_id": "edr-001",
    "severity": "critical",
    "title": "Suspicious process execution",
    "description": "Encoded powershell",
    "detected_at": "2026-10-06T12:00:00Z",
    "tactic": "execution",
    "technique_ids": ["T1059.001"],
    "device": {"id": "dev-1", "hostname": "WKSTN-01", "ip": "10.1.1.20", "os": "windows"},
    "user": {"name": "alice", "domain": "CORP"},
    "process": {
        "pid": 4321,
        "name": "powershell.exe",
        "command_line": "powershell.exe -enc AA==",
        "sha256": "ABC123",
        "parent": {"pid": 1000, "name": "explorer.exe"},
    },
}

WINDOWS_SECURITY = {
    "Event": {
        "System": {
            "Provider": {"Name": "Microsoft-Windows-Security-Auditing"},
            "EventID": 4624,
            "TimeCreated": {"SystemTime": "2026-10-06T12:00:00.0000000Z"},
            "Computer": "DC01.corp.local",
            "Channel": "Security",
            "EventRecordID": 55,
        },
        "EventData": {
            "TargetUserName": "alice",
            "TargetDomainName": "CORP",
            "IpAddress": "10.0.0.8",
            "LogonType": "10",
            "WorkstationName": "WKSTN-01",
        },
    }
}

WINDOWS_XML = """<?xml version="1.0" encoding="utf-8"?>
<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">
  <System>
    <Provider Name="Microsoft-Windows-Security-Auditing"/>
    <EventID>4688</EventID>
    <Level>0</Level>
    <TimeCreated SystemTime="2026-10-06T12:00:00.0000000Z"/>
    <EventRecordID>77</EventRecordID>
    <Channel>Security</Channel>
    <Computer>WKSTN-01</Computer>
  </System>
  <EventData>
    <Data Name="SubjectUserName">alice</Data>
    <Data Name="SubjectDomainName">CORP</Data>
    <Data Name="NewProcessName">C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe</Data>
    <Data Name="CommandLine">powershell.exe -enc AA==</Data>
    <Data Name="NewProcessId">0x10e1</Data>
    <Data Name="ParentProcessName">C:\\Windows\\explorer.exe</Data>
  </EventData>
</Event>
"""


def test_sigma_projects_rule_and_underlying_process() -> None:
    parsed = SigmaAlertParser().parse(json.dumps(SIGMA).encode())
    assert parsed.alert is not None
    assert parsed.alert.title == "Suspicious Encoded PowerShell"
    assert parsed.alert.severity == "high"
    assert parsed.alert.technique_ids == ("T1059.001",)
    assert parsed.alert.tactics == ("execution",)
    assert parsed.event.class_uid == 1007
    assert parsed.event.type_uid == 100701
    assert parsed.event.activity_name == "Launch"
    assert parsed.event.process is not None
    assert parsed.event.process.cmd_line == "powershell.exe -enc AA=="
    assert parsed.event.process.hashes[0].value == "abc123"
    assert parsed.event.process.hashes[0].algorithm_id == 3
    assert parsed.event.unmapped["sigma_rule_id"] == SIGMA["rule"]["id"]
    CanonicalEventDocument.model_validate(parsed.event.model_dump())


def test_sigma_without_a_match_is_a_detection_finding() -> None:
    payload = {
        "detected_at": "2026-10-06T12:00:00Z",
        "rule": {"id": "rule-1", "title": "Rare logon", "level": "medium", "tags": ["attack.t1078"]},
    }
    parsed = SigmaAlertParser().parse(json.dumps(payload).encode())
    assert parsed.event.class_uid == 2004
    assert parsed.event.type_uid == 200401
    assert parsed.event.activity_name == "Create"
    assert parsed.alert is not None
    assert parsed.alert.technique_ids == ("T1078",)


def test_sigma_rejects_invalid_json() -> None:
    with pytest.raises(IngestParseError) as caught:
        SigmaAlertParser().parse(b"not-json")
    assert caught.value.reason_code == "invalid_json"


def test_mock_edr_projects_process_alert() -> None:
    parsed = MockEdrParser().parse(json.dumps(EDR).encode())
    assert parsed.external_id == "edr-001"
    assert parsed.alert is not None
    assert parsed.alert.severity == "critical"
    assert parsed.event.class_name == "Process Activity"
    assert parsed.event.device is not None
    assert parsed.event.device.hostname == "WKSTN-01"
    assert parsed.event.user is not None
    assert parsed.event.process is not None
    assert parsed.event.process.parent_process is not None
    assert parsed.event.process.parent_process.name == "explorer.exe"
    assert any(item.type == "user" and item.value == r"CORP\alice" for item in parsed.event.observables)
    assert any(item.type == "hash" and item.value == "abc123" for item in parsed.event.observables)


def test_mock_edr_requires_alert_id() -> None:
    with pytest.raises(IngestParseError) as caught:
        MockEdrParser().parse(b'{"title": "x", "severity": "low", "detected_at": "2026-10-06T00:00:00Z"}')
    assert caught.value.reason_code == "schema_mismatch"


def test_windows_security_json_logon_keeps_seven_digit_fraction() -> None:
    parsed = WindowsEventParser().parse(json.dumps(WINDOWS_SECURITY).encode())
    assert parsed.alert is None
    assert parsed.event.class_uid == 3002
    assert parsed.event.type_uid == 300201
    assert parsed.event.status == "success"
    assert parsed.event.severity == "informational"
    assert "alice" in parsed.event.message
    assert parsed.event.time == int(datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert parsed.external_id == "DC01.corp.local:Security:55"


def test_windows_xml_process_create_accepts_utf16() -> None:
    parsed = WindowsEventParser().parse(WINDOWS_XML.encode("utf-16"))
    assert parsed.event.class_uid == 1007
    assert parsed.event.process is not None
    assert parsed.event.process.pid == 0x10E1
    assert parsed.event.process.cmd_line == "powershell.exe -enc AA=="
    assert parsed.event.user is not None
    assert parsed.event.user.domain == "CORP"


def test_windows_failed_logon_is_a_failure_outcome() -> None:
    payload = json.loads(json.dumps(WINDOWS_SECURITY))
    payload["Event"]["System"]["EventID"] = 4625
    parsed = WindowsEventParser().parse(json.dumps(payload).encode())
    assert parsed.event.status == "failure"
    assert parsed.event.severity == "medium"
    assert parsed.event.type_uid == 300201
