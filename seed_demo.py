"""Load the demo dataset through the operator CLI.

Steps:
1. Create two tenants. There is no tenant API, so this writes the rows directly.
2. Ingest every file in demo/payloads/ with ``soc-ingest ingest``.
3. Ingest one file a second time to show deduplication.
4. Set a few alert workflow statuses. There is no status API, so this uses SQL.
5. Replay one alert to show that replay keeps the analyst-owned status, and
   replay one broken file to show a replay dead letter.
6. Create cases, investigations, findings, and links with soc_platform.casework.

The script writes demo/state.json with the ids that run_agents.py and the
walkthrough use. Run it from the repository root after `alembic upgrade head`:

    python demo/make_payloads.py
    python demo/seed_demo.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
sys.path.insert(0, str(REPO))

from soc_platform import casework  # noqa: E402
from soc_platform.config import get_settings  # noqa: E402

TENANTS = {
    "cobalt-ridge": ("6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14", "Cobalt Ridge Logistics"),
    "ashgrove-clinic": ("2d8e4a71-9c3b-4e6f-a1d5-7b0c9e2f6a38", "Ashgrove Clinic"),
}
STATE = ROOT / "state.json"


def cli(*args: str) -> tuple[int, dict]:
    command = [sys.executable, "-m", "soc_platform.cli", *args]
    done = subprocess.run(command, cwd=REPO, capture_output=True, text=True, env={**os.environ, "SOC_LOG_FORMAT": "text"})
    out = done.stdout.strip().splitlines()
    if out and out[-1].startswith("{"):
        return done.returncode, json.loads(out[-1])
    errors = [line for line in done.stderr.strip().splitlines() if line.startswith("{")]
    return done.returncode, json.loads(errors[-1]) if errors else {"stderr": done.stderr.strip()}


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    with engine.begin() as connection:
        for slug, (tenant_id, name) in TENANTS.items():
            connection.execute(
                text(
                    "INSERT INTO tenants (id, slug, name, status, created_at, updated_at) "
                    "VALUES (:id, :slug, :name, 'active', now(), now()) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": tenant_id, "slug": slug, "name": name},
            )

    manifest = json.loads((ROOT / "payloads" / "manifest.json").read_text(encoding="utf-8"))
    state: dict = {"tenants": {slug: tenant_id for slug, (tenant_id, _) in TENANTS.items()}, "files": {}}
    totals = {"projected": 0, "dead_lettered": 0, "duplicate": 0, "rejected": 0}
    print(f"{'tenant':16} {'file':42} {'exit':>4}  result")
    for slug, items in manifest.items():
        tenant_id = TENANTS[slug][0]
        for item in items:
            path = ROOT / "payloads" / slug / item["file"]
            code, body = cli("ingest", "--tenant", tenant_id, "--kind", item["kind"], "--file", str(path))
            state["files"][f"{slug}/{item['file']}"] = body
            if code == 3:
                totals["rejected"] += 1
                outcome = body.get("error", "rejected")
            elif body.get("duplicate"):
                totals["duplicate"] += 1
                outcome = "duplicate"
            else:
                totals[body["receipt_status"]] += 1
                outcome = body["receipt_status"]
            print(f"{slug:16} {item['file']:42} {code:>4}  {outcome}")

    first = "cobalt-ridge/02-sigma-office-spawns-powershell.json"
    tenant_a = TENANTS["cobalt-ridge"][0]
    code, again = cli("ingest", "--tenant", tenant_a, "--kind", "sigma_alert", "--file", str(ROOT / "payloads" / first))
    print(f"\nRe-ingest {first}: exit {code}, duplicate={again['duplicate']}, same source record="
          f"{again['source_record_id'] == state['files'][first]['source_record_id']}")
    print("Totals:", totals)

    alert = lambda name: state["files"][f"cobalt-ridge/{name}"]["alert_id"]  # noqa: E731
    with engine.begin() as connection:
        for name in ("02-sigma-office-spawns-powershell.json", "03-edr-encoded-powershell.json", "05-edr-beaconing.json"):
            connection.execute(text("UPDATE alerts SET status = 'in_review' WHERE id = :id"), {"id": alert(name)})
            connection.execute(text("UPDATE alert_search_documents SET status = 'in_review' WHERE id = :id"), {"id": alert(name)})
        for name in ("27-edr-driver-blocked.json",):
            connection.execute(text("UPDATE alerts SET status = 'closed' WHERE id = :id"), {"id": alert(name)})
            connection.execute(text("UPDATE alert_search_documents SET status = 'closed' WHERE id = :id"), {"id": alert(name)})

    record = state["files"][first]["source_record_id"]
    code, replayed = cli("replay", "--tenant", tenant_a, "--source-record", record)
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT status, projection_generation FROM alerts WHERE id = :id"), {"id": alert(first.split("/")[1])}
        ).one()
    print(f"Replay {first}: exit {code}, receipt {replayed['receipt_status']}, "
          f"alert status {row.status}, projection_generation {row.projection_generation}")
    broken = state["files"]["cobalt-ridge/90-broken-sigma-truncated.json"]["source_record_id"]
    code, failed = cli("replay", "--tenant", tenant_a, "--source-record", broken)
    print(f"Replay of broken bytes: exit {code}, receipt {failed['receipt_status']}, dead_letter {failed['dead_letter_id']}")
    state["replay"] = {"ok": replayed, "failed": failed}

    with Session(engine) as session, session.begin():
        tid = UUID(tenant_a)
        case = casework.create_case(
            session, tenant_id=tid, title="INC-0412 Finance laptop compromise and data staging",
            severity="critical", assignee="Ana Torres", external_ref="INC-0412",
            description="Macro document on FIN-LT-07 led to credential theft, PsExec to FS-02, and an archive sent to 198.51.100.23.",
        )
        first_inv = casework.create_investigation(
            session, tenant_id=tid, case_id=case.id, priority="p1", assignee="Ana Torres",
            title="Initial access through Invoice_Q3_2026.docm on FIN-LT-07",
            hypothesis="The macro launched encoded PowerShell that beaconed to cdn-sync.example.",
        )
        second_inv = casework.create_investigation(
            session, tenant_id=tid, case_id=case.id, priority="p1", assignee="Ben Clarke",
            title="svc_backup used for lateral movement to FS-02",
            hypothesis="Credentials dumped from LSASS were used for PsExec and a temporary admin account.",
        )
        third_inv = casework.create_investigation(
            session, tenant_id=tid, case_id=case.id, priority="p2",
            title="Possible exfiltration of q3.7z to 198.51.100.23",
        )
        for inv, names in (
            (first_inv, ("02-sigma-office-spawns-powershell.json", "03-edr-encoded-powershell.json", "05-edr-beaconing.json")),
            (second_inv, ("07-edr-lsass-access.json", "09-sigma-failed-logons.json", "12-sigma-psexec-service.json", "16-sigma-admin-group-add.json")),
            (third_inv, ("19-edr-staging-archive.json", "22-edr-large-upload.json", "25-sigma-log-cleared.json")),
        ):
            for name in names:
                casework.link_alert_to_investigation(
                    session, tenant_id=tid, investigation_id=inv.id, alert_id=UUID(alert(name)), linked_by="Ana Torres"
                )
        finding = casework.create_finding(
            session, tenant_id=tid, case_id=case.id, investigation_id=first_inv.id,
            title="Macro document executed encoded PowerShell", severity="high", confidence=85,
            created_by="Ana Torres", technique_ids=["T1566.001", "T1059.001"], tactics=["initial_access", "execution"],
            summary="Sysmon, the Sigma match, and the EDR alert agree on WINWORD.EXE as the parent of powershell.exe.",
        )
        casework.link_alert_to_finding(
            session, tenant_id=tid, finding_id=finding.id,
            alert_id=UUID(alert("02-sigma-office-spawns-powershell.json")), linked_by="Ana Torres",
        )
        second_finding = casework.create_finding(
            session, tenant_id=tid, case_id=case.id, investigation_id=second_inv.id,
            title="svc_backup credentials are compromised", severity="critical", confidence=70,
            created_by="Ben Clarke", technique_ids=["T1003.001", "T1110.003"],
        )
        evidence = state["files"]["cobalt-ridge/02-sigma-office-spawns-powershell.json"]["evidence_id"]
        casework.link_evidence(session, tenant_id=tid, evidence_id=UUID(evidence), linked_by="Ana Torres",
                               investigation_id=first_inv.id, case_id=case.id)
        second_case = casework.create_case(
            session, tenant_id=tid, title="INC-0398 Unsigned driver blocked on HR-LT-03",
            severity="low", assignee="Ben Clarke", external_ref="INC-0398",
        )
        session.execute(
            text("UPDATE security_cases SET status = 'closed', closed_at = now() WHERE id = :id"), {"id": second_case.id}
        )
        session.execute(text("UPDATE investigations SET status = 'active' WHERE id IN (:a, :b)"),
                        {"a": first_inv.id, "b": second_inv.id})
        # Casework is created now; move its dates onto the story timeline so the console reads naturally.
        for table, row_id, column, when in (
            ("security_cases", case.id, "opened_at", "2026-10-06T08:30:00Z"),
            ("security_cases", second_case.id, "opened_at", "2026-10-09T10:20:00Z"),
            ("investigations", first_inv.id, "opened_at", "2026-10-05T10:05:00Z"),
            ("investigations", second_inv.id, "opened_at", "2026-10-06T09:10:00Z"),
            ("investigations", third_inv.id, "opened_at", "2026-10-09T03:15:00Z"),
            ("findings", finding.id, "created_at", "2026-10-06T11:40:00Z"),
            ("findings", second_finding.id, "created_at", "2026-10-07T04:00:00Z"),
        ):
            extra = ", created_at = :when" if column != "created_at" else ""
            session.execute(text(f"UPDATE {table} SET {column} = :when{extra} WHERE id = :id"), {"when": when, "id": row_id})
        session.execute(text("UPDATE security_cases SET closed_at = '2026-10-09T15:00:00Z' WHERE id = :id"),
                        {"id": second_case.id})
        state["casework"] = {
            "case": str(case.id), "closed_case": str(second_case.id),
            "investigations": [str(first_inv.id), str(second_inv.id), str(third_inv.id)],
            "findings": [str(finding.id), str(second_finding.id)],
        }
    state["seeded_at"] = datetime.now(timezone.utc).isoformat()
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    print(f"\nCasework created. State written to {STATE.relative_to(REPO)}")
    print(f"Console tenant: {tenant_a}")


if __name__ == "__main__":
    main()
