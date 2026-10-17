"""Drive the investigation workflow and the human decision through the HTTP API.

The API must be running on SOC_API_URL (default http://127.0.0.1:8000) and
seed_demo.py must have written demo/state.json. The script calls the API the
way the console's backend-for-frontend does, so requested_by and actor are
plain names here. The console fills them from the signed-in operator instead.

    python demo/run_agents.py
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
API = os.environ.get("SOC_API_URL", "http://127.0.0.1:8000")


def main() -> None:
    state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
    tenant = state["tenants"]["cobalt-ridge"]
    alert = lambda name: state["files"][f"cobalt-ridge/{name}"]["alert_id"]  # noqa: E731
    client = httpx.Client(base_url=API, params={"tenant": tenant}, timeout=60)
    runs: dict[str, dict] = {}

    def start(label: str, body: dict) -> dict:
        response = client.post("/api/v1/agent/runs", json=body)
        payload = response.json()
        if response.status_code != 201:
            print(f"{label:34} HTTP {response.status_code} {payload['error']['code']}")
            return payload
        draft = payload["draft"] or {}
        print(f"{label:34} HTTP 201 run={payload['status']:9} draft={draft.get('status', '-'):22} "
              f"claims={len(draft.get('claims', []))} error={payload['error_code']}")
        runs[label] = payload
        return payload

    def decide(label: str, draft_id: str, body: dict) -> dict:
        response = client.post(f"/api/v1/agent/drafts/{draft_id}/decisions", json=body)
        payload = response.json()
        detail = payload.get("status") or payload["error"]["code"]
        print(f"{label:34} HTTP {response.status_code} {detail}")
        return payload

    print("Investigation runs")
    office = start("Office spawning PowerShell", {"alert_id": alert("02-sigma-office-spawns-powershell.json"), "requested_by": "Ana Torres"})
    lsass = start("LSASS memory access", {"alert_id": alert("07-edr-lsass-access.json"), "requested_by": "Ana Torres"})
    start("Large outbound transfer", {"alert_id": alert("22-edr-large-upload.json"), "requested_by": "Ana Torres"})
    start("Unsigned driver (no technique)", {"alert_id": alert("27-edr-driver-blocked.json"), "requested_by": "Ben Clarke"})
    start("Question: svc_backup", {"question": "svc_backup", "requested_by": "Ana Torres"})
    start("Question: no matching records", {"question": "mimikatz", "requested_by": "Ana Torres"})
    start("Unknown alert id", {"alert_id": str(uuid.uuid4()), "requested_by": "Ana Torres"})
    start("Question that is a URL", {"question": "https://intel.example/ioc/203.0.113.45", "requested_by": "Ana Torres"})
    start("Agent name as requester", {"alert_id": alert("05-edr-beaconing.json"), "requested_by": "triage"})

    print("\nHuman decisions")
    decide("Approve Office draft", office["draft"]["id"], {"decision": "approved", "actor": "Ben Clarke", "note": "Claims match the stored alert, event, and evidence."})
    decide("Decide the same draft again", office["draft"]["id"], {"decision": "rejected", "actor": "Ben Clarke"})
    decide("Reject LSASS draft", lsass["draft"]["id"], {"decision": "rejected", "actor": "Ben Clarke", "note": "[changes-requested]\nAdd the 4625 burst on DC-01 before this goes to the case."})
    decide("Agent name as decider", runs["Large outbound transfer"]["draft"]["id"], {"decision": "approved", "actor": "reporting"})

    state["runs"] = {label: {"run_id": body["id"], "draft_id": (body.get("draft") or {}).get("id")} for label, body in runs.items()}
    (ROOT / "state.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    sample = office["draft"]["claims"]
    print(f"\nClaims in the approved draft ({len(sample)}):")
    for claim in sample:
        print(" -", claim["statement"])


if __name__ == "__main__":
    main()
