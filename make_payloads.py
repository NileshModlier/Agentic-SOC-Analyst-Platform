"""Write the demo payloads to demo/payloads/.

The story is fictional. Cobalt Ridge Logistics (Windows domain CRL) suffers a
five-day intrusion that starts with a macro document on a finance laptop and
ends with data staged and sent to an outside host. External addresses come from
the documentation ranges in RFC 5737, and names use the reserved .example TLD.

Every file is a raw payload in one of the formats the intake parsers accept:

* sigma_alert     Sigma rule-match JSON, with or without the matched event
* mock_edr_alert  the stand-in EDR alert JSON
* windows_event   Windows Event XML (UTF-8 or UTF-16), Event JSON, or Winlogbeat JSON

Four files are broken on purpose so the dead-letter path has something to show.
The second tenant receives one file whose bytes are identical to a first-tenant
file, which shows that deduplication is per tenant.

Run:  python demo/make_payloads.py
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "payloads"

TENANT_A = "cobalt-ridge"
TENANT_B = "ashgrove-clinic"

C2_IP = "203.0.113.45"
C2_HOST = "cdn-sync.example"
EXFIL_IP = "198.51.100.23"

LAPTOP = ("FIN-LT-07", "10.40.12.57")
FILESERVER = ("FS-02", "10.40.2.20")
DC = ("DC-01", "10.40.1.10")
HR_LAPTOP = ("HR-LT-03", "10.40.14.33")

ENCODED = base64.b64encode("Start-Sleep 1 # demo placeholder".encode("utf-16-le")).decode()


# --------------------------------------------------------------------------- formats


def winlogbeat(ts: str, host: str, provider: str, channel: str, event_id: int, record: int, data: dict) -> bytes:
    body = {
        "@timestamp": ts,
        "host": {"hostname": host},
        "event": {"code": str(event_id), "provider": provider},
        "winlog": {
            "channel": channel,
            "provider_name": provider,
            "event_id": event_id,
            "computer_name": host,
            "record_id": record,
            "event_data": data,
        },
    }
    return json.dumps(body, indent=2).encode()


def event_json_doc(ts: str, host: str, provider: str, channel: str, event_id: int, record: int, data: dict) -> dict:
    return {
        "Event": {
            "System": {
                "Provider": {"Name": provider},
                "EventID": event_id,
                "Level": 0,
                "TimeCreated": {"SystemTime": ts},
                "EventRecordID": record,
                "Channel": channel,
                "Computer": host,
            },
            "EventData": data,
        }
    }


def event_json(*args) -> bytes:
    return json.dumps(event_json_doc(*args), indent=2).encode()


def event_xml(ts: str, host: str, provider: str, channel: str, event_id: int, record: int, data: dict, *, level: int = 0, encoding: str = "utf-8") -> bytes:
    rows = "\n".join(f'    <Data Name="{name}">{_xml_escape(str(value))}</Data>' for name, value in data.items())
    text = (
        f'<?xml version="1.0" encoding="{encoding}"?>\n'
        '<Event xmlns="http://schemas.microsoft.com/win/2004/08/events/event">\n'
        "  <System>\n"
        f'    <Provider Name="{provider}"/>\n'
        f"    <EventID>{event_id}</EventID>\n"
        f"    <Level>{level}</Level>\n"
        f'    <TimeCreated SystemTime="{ts}"/>\n'
        f"    <EventRecordID>{record}</EventRecordID>\n"
        f"    <Channel>{channel}</Channel>\n"
        f"    <Computer>{host}</Computer>\n"
        "  </System>\n"
        "  <EventData>\n"
        f"{rows}\n"
        "  </EventData>\n"
        "</Event>\n"
    )
    return text.encode("utf-16") if encoding == "utf-16" else text.encode("utf-8")


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def sigma(alert_id: str, detected_at: str, rule: dict, matched: dict | None = None) -> bytes:
    body: dict = {"alert_id": alert_id, "detected_at": detected_at, "rule": rule}
    if matched is not None:
        body["event"] = matched
    return json.dumps(body, indent=2).encode()


def edr(**fields) -> bytes:
    body = {"vendor": "mock-edr", "product": "MockEDR"}
    body.update(fields)
    return json.dumps(body, indent=2).encode()


SECURITY = ("Microsoft-Windows-Security-Auditing", "Security")
SYSMON = ("Microsoft-Windows-Sysmon", "Microsoft-Windows-Sysmon/Operational")
SCM = ("Service Control Manager", "System")
EVENTLOG = ("Microsoft-Windows-Eventlog", "Security")


# --------------------------------------------------------------------------- tenant A


def tenant_a() -> list[tuple[str, str, bytes]]:
    files: list[tuple[str, str, bytes]] = []

    def add(name: str, kind: str, payload: bytes) -> None:
        files.append((name, kind, payload))

    # Day 1, 5 October: a macro document launches encoded PowerShell, which beacons out.
    add("01-logon-okafor.xml", "windows_event", event_xml(
        "2026-10-05T08:02:11.4410000Z", LAPTOP[0], *SECURITY, 4624, 18231,
        {"TargetUserName": "m.okafor", "TargetDomainName": "CRL", "LogonType": "2",
         "IpAddress": "-", "WorkstationName": LAPTOP[0]},
    ))
    sysmon_ps = {
        "Image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
        "CommandLine": f"powershell.exe -nop -w hidden -enc {ENCODED}",
        "User": r"CRL\m.okafor",
        "ProcessId": "7412",
        "ParentImage": r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
        "ParentCommandLine": r'"WINWORD.EXE" /n "C:\Users\m.okafor\Downloads\Invoice_Q3_2026.docm"',
        "ParentProcessId": "6120",
        "Hashes": "SHA256=9F2C6A1E5B7D3C08A4E6F1B2D3C4A5B6C7D8E9F0A1B2C3D4E5F6A7B8C9D0E1F2",
    }
    add("02-sigma-office-spawns-powershell.json", "sigma_alert", sigma(
        "sig-20261005-0001", "2026-10-05T09:14:03Z",
        {
            "id": "438025f9-5856-4663-83f7-52f878a70a50",
            "title": "Office Application Spawning PowerShell",
            "level": "high",
            "description": "WINWORD.EXE started powershell.exe with an encoded command (T1059.001 after T1566.001).",
            "tags": ["attack.execution", "attack.t1059.001", "attack.initial_access", "attack.t1566.001"],
            "logsource": {"product": "windows", "category": "process_creation"},
        },
        json.loads(winlogbeat("2026-10-05T09:14:02.118Z", LAPTOP[0], *SYSMON, 1, 552301, sysmon_ps)),
    ))
    add("03-edr-encoded-powershell.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0001", severity="high", title="Encoded PowerShell command",
        description="PowerShell started hidden with -enc by a Word process.",
        detected_at="2026-10-05T09:14:05Z", tactic="execution", technique_ids=["T1059.001"],
        device={"id": "dev-fin-lt-07", "hostname": LAPTOP[0], "ip": LAPTOP[1], "os": "windows"},
        user={"name": "m.okafor", "domain": "CRL"},
        process={"pid": 7412, "name": "powershell.exe",
                 "path": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                 "command_line": f"powershell.exe -nop -w hidden -enc {ENCODED}",
                 "sha256": "9f2c6a1e5b7d3c08a4e6f1b2d3c4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2",
                 "parent": {"pid": 6120, "name": "WINWORD.EXE"}},
    ))
    add("04-sysmon-network-c2.json", "windows_event", winlogbeat(
        "2026-10-05T09:14:31.902Z", LAPTOP[0], *SYSMON, 3, 552317,
        {"Image": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "User": r"CRL\m.okafor",
         "ProcessId": "7412", "SourceIp": LAPTOP[1], "SourcePort": "52144",
         "DestinationIp": C2_IP, "DestinationPort": "443", "DestinationHostname": C2_HOST},
    ))
    add("05-edr-beaconing.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0002", severity="high", title="Beaconing to rare external host",
        description=f"Regular 60-second HTTPS connections to {C2_HOST} ({C2_IP}), first seen today.",
        detected_at="2026-10-05T09:20:00Z", tactic="command-and-control", technique_ids=["T1071.001"],
        device={"id": "dev-fin-lt-07", "hostname": LAPTOP[0], "ip": LAPTOP[1], "os": "windows"},
        network={"src_ip": LAPTOP[1], "src_port": 52144, "dst_ip": C2_IP, "dst_port": 443, "dst_hostname": C2_HOST},
    ))
    add("06-logoff-okafor.json", "windows_event", event_json(
        "2026-10-05T17:45:09.0000000Z", LAPTOP[0], *SECURITY, 4634, 18977,
        {"TargetUserName": "m.okafor", "TargetDomainName": "CRL", "LogonType": "2"},
    ))

    # Day 2, 6 October: LSASS is dumped, then svc_backup is guessed and used.
    add("07-edr-lsass-access.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0003", severity="critical", title="LSASS memory access",
        description="rundll32 loaded comsvcs.dll MiniDump against the LSASS process.",
        detected_at="2026-10-06T02:11:40Z", tactic="credential-access", technique_ids=["T1003.001"],
        device={"id": "dev-fin-lt-07", "hostname": LAPTOP[0], "ip": LAPTOP[1], "os": "windows"},
        user={"name": "m.okafor", "domain": "CRL"},
        process={"pid": 9024, "name": "rundll32.exe", "path": r"C:\Windows\System32\rundll32.exe",
                 "command_line": r"rundll32.exe C:\Windows\System32\comsvcs.dll, MiniDump 724 C:\Users\Public\l.dmp full",
                 "parent": {"pid": 7412, "name": "powershell.exe"}},
    ))
    for offset, (second, record) in enumerate(((5, 88120), (11, 88121), (17, 88124), (24, 88127)), start=1):
        add(f"08-failed-logon-svc-backup-{offset}.json", "windows_event", event_json(
            f"2026-10-06T02:31:{second:02d}.5530000Z", DC[0], *SECURITY, 4625, record,
            {"TargetUserName": "svc_backup", "TargetDomainName": "CRL", "LogonType": "3",
             "IpAddress": LAPTOP[1], "IpPort": "0", "WorkstationName": LAPTOP[0],
             "Status": "0xc000006d", "SubStatus": "0xc000006a"},
        ))
    add("09-sigma-failed-logons.json", "sigma_alert", sigma(
        "sig-20261006-0002", "2026-10-06T02:32:00Z",
        {
            "id": "e98374a6-e2d9-4076-9b5c-11bdb2569995",
            "title": "Multiple Failed Logons for One Account",
            "level": "medium",
            "description": r"Four 4625 events for CRL\svc_backup from 10.40.12.57 within 30 seconds.",
            "tags": ["attack.credential_access", "attack.t1110.003"],
            "logsource": {"product": "windows", "service": "security"},
        },
    ))
    add("10-logon-svc-backup-fs02.xml", "windows_event", event_xml(
        "2026-10-06T02:33:48.1020000Z", FILESERVER[0], *SECURITY, 4624, 40211,
        {"TargetUserName": "svc_backup", "TargetDomainName": "CRL", "LogonType": "3",
         "IpAddress": LAPTOP[1], "IpPort": "53011", "WorkstationName": LAPTOP[0]},
    ))

    # Day 3, 7 October: PsExec onto the file server, discovery, and a new admin account.
    service = {"ServiceName": "PSEXESVC", "ImagePath": r"%SystemRoot%\PSEXESVC.exe",
               "ServiceType": "user mode service", "StartType": "demand start", "AccountName": "LocalSystem"}
    add("11-service-install-psexesvc.xml", "windows_event", event_xml(
        "2026-10-07T03:05:12.0000000Z", FILESERVER[0], *SCM, 7045, 9921, service, level=4, encoding="utf-16",
    ))
    add("12-sigma-psexec-service.json", "sigma_alert", sigma(
        "sig-20261007-0003", "2026-10-07T03:05:14Z",
        {
            "id": "42c575ea-e41e-41f1-b248-8093c3e82a28",
            "title": "PsExec Service Installation",
            "level": "high",
            "description": "The PSEXESVC service was installed, which PsExec does before running a remote command.",
            "tags": ["attack.execution", "attack.t1569.002", "attack.lateral_movement", "attack.t1021.002"],
            "logsource": {"product": "windows", "service": "system"},
        },
        event_json_doc("2026-10-07T03:05:12.0000000Z", FILESERVER[0], *SCM, 7045, 9921, service),
    ))
    add("13-process-net-group.xml", "windows_event", event_xml(
        "2026-10-07T03:07:40.2200000Z", FILESERVER[0], *SECURITY, 4688, 40388,
        {"SubjectUserName": "svc_backup", "SubjectDomainName": "CRL",
         "NewProcessName": r"C:\Windows\System32\cmd.exe",
         "CommandLine": r'cmd.exe /c net group "Domain Admins" /domain',
         "NewProcessId": "0x1a3c", "ParentProcessName": r"C:\Windows\PSEXESVC.exe"},
    ))
    add("14-user-created-helpdesk-tmp.json", "windows_event", event_json(
        "2026-10-07T03:12:02.7000000Z", DC[0], *SECURITY, 4720, 88544,
        {"TargetUserName": "helpdesk_tmp", "TargetDomainName": "CRL",
         "SubjectUserName": "svc_backup", "SubjectDomainName": "CRL"},
    ))
    member_added = {"MemberName": "CN=helpdesk_tmp,OU=Staff,DC=corp,DC=cobaltridge,DC=example",
                    "TargetUserName": "Administrators", "TargetDomainName": "Builtin",
                    "SubjectUserName": "svc_backup", "SubjectDomainName": "CRL"}
    add("15-group-member-added.json", "windows_event", event_json(
        "2026-10-07T03:12:30.1000000Z", DC[0], *SECURITY, 4732, 88547, member_added,
    ))
    add("16-sigma-admin-group-add.json", "sigma_alert", sigma(
        "sig-20261007-0004", "2026-10-07T03:13:00Z",
        {
            "id": "ffa28e60-bdb1-46e0-9f82-05f7a61cc06e",
            "title": "User Added to Local Administrators",
            "level": "medium",
            "description": "A newly created account was added to the built-in Administrators group.",
            "tags": ["attack.persistence", "attack.t1098", "attack.t1136.001"],
            "logsource": {"product": "windows", "service": "security"},
        },
        json.loads(winlogbeat("2026-10-07T03:12:30.100Z", DC[0], *SECURITY, 4732, 88547, member_added)),
    ))

    # Day 4, 8 October: data is compressed into a staging folder.
    add("17-sysmon-7z-archive.json", "windows_event", winlogbeat(
        "2026-10-08T01:40:19.330Z", FILESERVER[0], *SYSMON, 1, 77120,
        {"Image": r"C:\ProgramData\stage\7z.exe",
         "CommandLine": r"7z.exe a -mx9 -p C:\ProgramData\stage\q3.7z \\FS-02\Finance$\*",
         "User": r"CRL\svc_backup", "ProcessId": "5120", "ParentImage": r"C:\Windows\System32\cmd.exe"},
    ))
    add("18-sysmon-file-created.json", "windows_event", winlogbeat(
        "2026-10-08T01:52:04.010Z", FILESERVER[0], *SYSMON, 11, 77198,
        {"Image": r"C:\ProgramData\stage\7z.exe", "TargetFilename": r"C:\ProgramData\stage\q3.7z",
         "User": r"CRL\svc_backup", "ProcessId": "5120"},
    ))
    add("19-edr-staging-archive.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0004", severity="medium", title="Archive created in staging directory",
        description=r"A password-protected 7z archive of \\FS-02\Finance$ was written under C:\ProgramData\stage.",
        detected_at="2026-10-08T01:52:30Z", tactic="collection", technique_ids=["T1560.001"],
        device={"id": "dev-fs-02", "hostname": FILESERVER[0], "ip": FILESERVER[1], "os": "windows"},
        user={"name": "svc_backup", "domain": "CRL"},
        process={"pid": 5120, "name": "7z.exe", "path": r"C:\ProgramData\stage\7z.exe",
                 "command_line": r"7z.exe a -mx9 -p C:\ProgramData\stage\q3.7z \\FS-02\Finance$\*",
                 "parent": {"pid": 4410, "name": "cmd.exe"}},
    ))
    add("20-logon-lindqvist.xml", "windows_event", event_xml(
        "2026-10-08T09:00:27.0000000Z", HR_LAPTOP[0], *SECURITY, 4624, 30115,
        {"TargetUserName": "j.lindqvist", "TargetDomainName": "CRL", "LogonType": "2",
         "IpAddress": "-", "WorkstationName": HR_LAPTOP[0]},
    ))

    # Day 5, 9 October: the archive leaves, the log is cleared, and the account is removed.
    add("21-sysmon-network-exfil.json", "windows_event", winlogbeat(
        "2026-10-09T02:19:55.640Z", FILESERVER[0], *SYSMON, 3, 78002,
        {"Image": r"C:\ProgramData\stage\rclone.exe", "User": r"CRL\svc_backup", "ProcessId": "6644",
         "SourceIp": FILESERVER[1], "SourcePort": "61022", "DestinationIp": EXFIL_IP, "DestinationPort": "443"},
    ))
    add("22-edr-large-upload.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0005", severity="high", title="Large outbound transfer to rare host",
        description=f"2.4 GB sent over HTTPS to {EXFIL_IP}, an address not seen before in this tenant.",
        detected_at="2026-10-09T02:20:40Z", tactic="exfiltration", technique_ids=["T1041"],
        device={"id": "dev-fs-02", "hostname": FILESERVER[0], "ip": FILESERVER[1], "os": "windows"},
        network={"src_ip": FILESERVER[1], "src_port": 61022, "dst_ip": EXFIL_IP, "dst_port": 443},
    ))
    add("23-process-terminated-rclone.xml", "windows_event", event_xml(
        "2026-10-09T02:30:02.0000000Z", FILESERVER[0], *SECURITY, 4689, 41020,
        {"SubjectUserName": "svc_backup", "SubjectDomainName": "CRL",
         "ProcessName": r"C:\ProgramData\stage\rclone.exe", "ProcessId": "0x19f4"},
    ))
    cleared = {"SubjectUserName": "svc_backup", "SubjectDomainName": "CRL"}
    add("24-security-log-cleared.xml", "windows_event", event_xml(
        "2026-10-09T02:41:00.0000000Z", FILESERVER[0], *EVENTLOG, 1102, 41077, cleared, level=4,
    ))
    add("25-sigma-log-cleared.json", "sigma_alert", sigma(
        "sig-20261009-0005", "2026-10-09T02:41:03Z",
        {
            "id": "f2b7e0a5-9c4e-4d1a-8b6f-3e2a1c0d9b87",
            "title": "Security Event Log Cleared",
            "level": "high",
            "description": "The Security log on a server was cleared by a service account.",
            "tags": ["attack.defense_evasion", "attack.t1070.001"],
            "logsource": {"product": "windows", "service": "security"},
        },
        event_json_doc("2026-10-09T02:41:00.0000000Z", FILESERVER[0], *EVENTLOG, 1102, 41077, cleared),
    ))
    add("26-user-deleted-helpdesk-tmp.json", "windows_event", event_json(
        "2026-10-09T02:45:31.0000000Z", DC[0], *SECURITY, 4726, 89310,
        {"TargetUserName": "helpdesk_tmp", "TargetDomainName": "CRL",
         "SubjectUserName": "svc_backup", "SubjectDomainName": "CRL"},
    ))
    add("27-edr-driver-blocked.json", "mock_edr_alert", edr(
        alert_id="edr-7f3a-0006", severity="low", title="Unsigned driver load blocked",
        description="A printer utility tried to load an unsigned driver. The load was blocked.",
        detected_at="2026-10-09T10:05:00Z",
        device={"id": "dev-hr-lt-03", "hostname": HR_LAPTOP[0], "ip": HR_LAPTOP[1], "os": "windows"},
        user={"name": "j.lindqvist", "domain": "CRL"},
    ))

    # Broken on purpose. Each is stored, then dead-lettered with a reason code.
    add("90-broken-sigma-truncated.json", "sigma_alert",
        b'{"alert_id": "sig-broken-1", "detected_at": "2026-10-09T03:00:00Z", "rule": {"title": "Truncated')
    add("91-broken-edr-no-alert-id.json", "mock_edr_alert", edr(
        severity="medium", title="Alert without an id", detected_at="2026-10-09T03:01:00Z"))
    add("92-broken-windows-xml.xml", "windows_event",
        b'<?xml version="1.0"?><Event><System><EventID>4624</EventID></System><EventData>')
    add("93-broken-windows-no-time.json", "windows_event", json.dumps(
        {"Event": {"System": {"Provider": {"Name": SECURITY[0]}, "EventID": 4624, "Computer": DC[0],
                              "Channel": "Security", "EventRecordID": 99001},
                   "EventData": {"TargetUserName": "svc_backup"}}}, indent=2).encode())
    return files


def tenant_b(shared: bytes) -> list[tuple[str, str, bytes]]:
    return [
        ("01-shared-bytes.xml", "windows_event", shared),
        ("02-sigma-rdp-logon.json", "sigma_alert", sigma(
            "sig-ash-0001", "2026-10-08T14:22:00Z",
            {"id": "c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f", "title": "Remote Desktop Logon from Public Address",
             "level": "medium", "tags": ["attack.initial_access", "attack.t1133"],
             "logsource": {"product": "windows", "service": "security"}},
        )),
    ]


def main() -> None:
    a = tenant_a()
    shared = next(payload for name, _, payload in a if name.startswith("20-"))
    b = tenant_b(shared)
    manifest = {}
    for tenant, files in ((TENANT_A, a), (TENANT_B, b)):
        folder = ROOT / tenant
        folder.mkdir(parents=True, exist_ok=True)
        for stale in folder.iterdir():
            stale.unlink()
        for name, kind, payload in files:
            (folder / name).write_bytes(payload)
        manifest[tenant] = [{"file": name, "kind": kind} for name, kind, _ in files]
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for tenant, items in manifest.items():
        kinds: dict[str, int] = {}
        for item in items:
            kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
        print(f"{tenant}: {len(items)} payloads {kinds}")


if __name__ == "__main__":
    main()
