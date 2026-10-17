# Demo walkthrough

A guided 15-minute demo of the whole platform: intake, dead letters and replay, search, an investigation run, a human decision, administration and metrics. Every number below was produced by running these exact steps on a fresh database.

- [The story](#the-story)
- [0. Start the platform](#0-start-the-platform)
- [1. Intake: 36 payloads, 4 broken on purpose](#1-intake-36-payloads-4-broken-on-purpose)
- [2. Replay](#2-replay)
- [3. Investigations and decisions through the API](#3-investigations-and-decisions-through-the-api)
- [4. Analyst in the console](#4-analyst-in-the-console)
- [5. Run an investigation from the console](#5-run-an-investigation-from-the-console)
- [6. Reviewer](#6-reviewer)
- [7. Administrator](#7-administrator)
- [8. Metrics and alert rules](#8-metrics-and-alert-rules)
- [Talking points](#talking-points)
- [Reset](#reset)

---

## The story

**Cobalt Ridge Logistics** (fictional; Windows domain `CRL`) suffers a five-day intrusion. External addresses come from the RFC 5737 documentation ranges and names use `.example`.

| Day | What happens | Payloads in `demo/payloads/cobalt-ridge/` |
| --- | --- | --- |
| Mon 5 Oct | `m.okafor` opens `Invoice_Q3_2026.docm` on `FIN-LT-07`; Word starts hidden, encoded PowerShell, which beacons to `cdn-sync.example` (`203.0.113.45`) | 01 logon (XML), 02 Sigma "Office Application Spawning PowerShell" with the Sysmon 1 event, 03 EDR "Encoded PowerShell command", 04 Sysmon 3 (Winlogbeat), 05 EDR "Beaconing to rare external host", 06 logoff (Event JSON) |
| Tue 6 Oct | LSASS is dumped with `comsvcs.dll`; four failed logons for `svc_backup` on `DC-01` from the laptop, then a successful network logon to `FS-02` | 07 EDR "LSASS memory access" (critical), 08 four 4625 events, 09 Sigma "Multiple Failed Logons for One Account" (no matched event), 10 4624 (XML) |
| Wed 7 Oct | PsExec onto `FS-02`, `net group "Domain Admins"`, a new account `helpdesk_tmp` added to Administrators | 11 7045 **UTF-16 XML**, 12 Sigma "PsExec Service Installation", 13 4688, 14 4720, 15 4732, 16 Sigma "User Added to Local Administrators" |
| Thu 8 Oct | Finance share compressed into `C:\ProgramData\stage\q3.7z`; a benign HR logon | 17 Sysmon 1, 18 Sysmon 11, 19 EDR "Archive created in staging directory", 20 4624 |
| Fri 9 Oct | 2.4 GB sent to `198.51.100.23`, Security log cleared, `helpdesk_tmp` deleted; an unrelated blocked driver | 21 Sysmon 3, 22 EDR "Large outbound transfer to rare host", 23 4689, 24 1102, 25 Sigma "Security Event Log Cleared", 26 4726, 27 EDR "Unsigned driver load blocked" (no technique) |
| | Broken on purpose | 90 truncated Sigma JSON, 91 EDR without `alert_id`, 92 malformed XML, 93 Event JSON without `TimeCreated` |

A second tenant, **Ashgrove Clinic**, receives two payloads. One is byte-for-byte identical to Cobalt Ridge's file 20, to show that deduplication is per tenant.

---

## 0. Start the platform

```bash
docker compose up -d --build
python -m venv .venv && source .venv/bin/activate && pip install -e '.[dev]'
cp .env.example .env
cd console && cp .env.example .env.local && npm ci && npm run dev    # in a second terminal
```

Check: `curl -s localhost:8000/ready` returns `{"status":"ok","postgres":"ok","redis":"ok"}`.

---

## 1. Intake: 36 payloads, 4 broken on purpose

```bash
python demo/make_payloads.py
python demo/seed_demo.py
```

```text
cobalt-ridge: 34 payloads {'windows_event': 21, 'sigma_alert': 6, 'mock_edr_alert': 7}
ashgrove-clinic: 2 payloads {'windows_event': 1, 'sigma_alert': 1}
tenant           file                                       exit  result
cobalt-ridge     01-logon-okafor.xml                           0  projected
cobalt-ridge     02-sigma-office-spawns-powershell.json        0  projected
…
cobalt-ridge     27-edr-driver-blocked.json                    0  projected
cobalt-ridge     90-broken-sigma-truncated.json                2  dead_lettered
cobalt-ridge     91-broken-edr-no-alert-id.json                2  dead_lettered
cobalt-ridge     92-broken-windows-xml.xml                     2  dead_lettered
cobalt-ridge     93-broken-windows-no-time.json                2  dead_lettered
ashgrove-clinic  01-shared-bytes.xml                           0  projected
ashgrove-clinic  02-sigma-rdp-logon.json                       0  projected

Re-ingest cobalt-ridge/02-sigma-office-spawns-powershell.json: exit 0, duplicate=True, same source record=True
Totals: {'projected': 32, 'dead_lettered': 4, 'duplicate': 0, 'rejected': 0}
```

What to point out:

- Each line is one `soc-ingest ingest` process and one database transaction. Exit `2` means the bytes were **stored** and dead-lettered, not lost.
- The four reason codes: `invalid_json`, `schema_mismatch` (EDR alert is missing `alert_id`), `invalid_xml`, `missing_timestamp`.
- Re-ingesting identical bytes returns the existing record with `duplicate: true` and writes nothing.
- Ashgrove's first file has the same SHA-256 as a Cobalt Ridge file and is still projected: deduplication is per tenant.
- Cobalt Ridge now has 30 canonical events, 11 alerts (5 Sigma, 6 EDR) and 25 catalogue entities (5 users, 4 hosts, 10 processes, 1 file, 5 IPs).

Inspect a result directly:

```bash
T=6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14
curl -s "localhost:8000/api/v1/operations/connectors?tenant=$T"
# Sigma 5 projected / 1 dead-lettered, EDR 6 / 1, Windows 19 / 2
```

The seed also sets three alerts to `in_review` and one to `closed` with SQL (there is no status endpoint), and creates two cases, three investigations, two findings and their links with `soc_platform.casework`, with dates on the story timeline.

---

## 2. Replay

The seed then replays two records:

```text
Replay cobalt-ridge/02-sigma-office-spawns-powershell.json: exit 0, receipt projected, alert status in_review, projection_generation 2
Replay of broken bytes: exit 2, receipt dead_lettered, dead_letter 000d3468-…
```

- Replay re-parses the **stored** bytes. The alert's `projection_generation` rises to 2, and its analyst-owned `in_review` status survives.
- Replaying the truncated Sigma file fails again, so a second dead letter with stage `replay` and `attempt_count: 2` is added, and the earlier projection (none, here) is left alone.
- Both replays write outbox rows (`ingest.replayed`, `ingest.replay_failed`). With the relay running, the stream holds 38 entries: 36 intakes and 2 replays.

```bash
redis-cli XLEN soc.outbox          # 38
redis-cli XRANGE soc.outbox - + COUNT 1
```

Manual equivalent: `soc-ingest replay --tenant $T --source-record <uuid>`.

---

## 3. Investigations and decisions through the API

```bash
python demo/run_agents.py
```

```text
Investigation runs
Office spawning PowerShell         HTTP 201 run=completed draft=pending_approval       claims=9 error=None
LSASS memory access                HTTP 201 run=completed draft=pending_approval       claims=9 error=None
Large outbound transfer            HTTP 201 run=completed draft=pending_approval       claims=7 error=None
Unsigned driver (no technique)     HTTP 201 run=completed draft=pending_approval       claims=7 error=None
Question: svc_backup               HTTP 201 run=completed draft=pending_approval       claims=18 error=None
Question: no matching records      HTTP 201 run=completed draft=insufficient_evidence  claims=0 error=None
Unknown alert id                   HTTP 201 run=failed    draft=-                      claims=0 error=alert_not_found
Question that is a URL             HTTP 422 network_denied
Agent name as requester            HTTP 422 validation_error

Human decisions
Approve Office draft               HTTP 200 approved
Decide the same draft again        HTTP 409 conflict
Reject LSASS draft                 HTTP 200 rejected
Agent name as decider              HTTP 422 validation_error

Claims in the approved draft (9):
 - Stored alert ea57ccdd-… is titled Office Application Spawning PowerShell with severity high and status in_review.
 - Stored alert ea57ccdd-… records technique T1059.001.
 - Stored alert ea57ccdd-… records technique T1566.001.
 - Stored event c9467d64-… is Process Activity with severity informational: Process C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe launched by CRL\m.okafor: powershell.exe -nop -w hidden -enc …
 - Stored evidence cf59568c-… is raw_payload with sha256 ba7d48d3….
 - Stored user CRL\m.okafor is linked to 6 events with highest severity critical.
 - Stored host FIN-LT-07 is linked to 7 events with highest severity critical.
 - Stored process C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe is linked to 3 events with highest severity high.
 - Stored process C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE is linked to 1 events with highest severity informational.
```

What to point out:

- Every sentence is a template filled from a stored row, and the reporting agent reloaded each row before saving the draft.
- The unsigned-driver alert has no technique, so the draft says so with the `alert.no_technique` template rather than guessing one.
- `mimikatz` matches nothing, so the run ends `insufficient_evidence`. An unknown alert id fails and stores no draft.
- A URL question is refused before a run exists. Agent names cannot act as people.
- The LSASS draft is rejected with a note that starts `[changes-requested]`, which is how the console stores "request changes".
- Look at the threat agent's work in `GET /api/v1/agent/runs/{id}`: it searched `T1059.001` and found only the Sigma alert whose description mentions it, not the EDR alert that stores the same technique. That is README gap 4.

---

## 4. Analyst in the console

Open <http://localhost:3000/login>, choose **Analyst**, password `analyst-local`, tenant `6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14`.

1. **Dashboard.** Seven open alerts, seven high or critical, one active case, three pending reviews, three open or active investigations; alert trend across 5 to 9 October. Read the page note: the cards count the latest page of up to 100 rows, the facets count everything.
2. **Alerts.** Eleven alerts. Click **critical** in the Severity facet: only "LSASS memory access". Clear it. Type `203.0.113.45` in the search box: only "Beaconing to rare external host". Try `powershell.exe` and `svc_backup`.
3. Open **Office Application Spawning PowerShell**. The left panel is the Sigma detection; the right is the canonical event, a Process Activity: Launch by `CRL\m.okafor`.
4. **Entities → Users → `CRL\svc_backup`.** Thirteen linked events from 6 to 9 October and the related alerts.
5. **Cases → INC-0412.** Three investigations and two findings (you may see the stale "Loading investigation" rows from gap 10).
6. **Investigations → "svc_backup used for lateral movement to FS-02".** The timeline merges the investigation, its four alerts, and any agent runs on them.

---

## 5. Run an investigation from the console

1. **Alerts → "User Added to Local Administrators" → Run investigation.** The workspace opens with the alert id filled in.
2. Click **Run investigation**. The run completes in well under a second; the draft is `pending_approval` with seven claims: the alert, techniques `T1098` and `T1136.001`, the 4732 event, the custody record, and the entities `Builtin\Administrators` and `DC-01`.
3. Scroll to **Agent memory**: supervisor plan, triage observations and claims, entity lookups, threat searches, reporting.
4. In **Recent runs**, open "Draft: mimikatz" (insufficient evidence) and the failed run named by its alert id (`alert_not_found`).
5. Open **Sentinel** in the corner. It explains the supervisor and each specialist on this page and says it does not call a model.

The console sent `requested_by: "Analyst"`, taken from the session, not from the browser.

---

## 6. Reviewer

Sign out, then sign in as **Reviewer** (`reviewer-local`, same tenant).

1. **Review queue.** Select "Draft: User Added to Local Administrators". Read the claims and their `alert:…`, `event:…`, `evidence:…`, `entity:…` citations.
2. Type a note and click **Approve**. The draft becomes `approved`, and the decision line shows "Reviewer", the time and your note. Open the alert again: its status has not changed, and no finding was created.
3. **Separation of duties.** In the agent workspace, run an investigation yourself on "Multiple Failed Logons for One Account". Back in the review queue, open that draft and click **Approve**: "The person who requested the investigation cannot decide the draft."
4. Try **Reject** with an empty note: the console asks for one. **Request changes** with a note is recorded as a rejection and shown as "Changes requested".
5. Sign in as Analyst and visit `/reviews`: you are sent back to the dashboard.

---

## 7. Administrator

Sign in as **Administrator** (`admin-local`).

1. **Administration.** Connector health (Sigma 5/1, EDR 6/1, Windows 19/2), dead letters with stage and reason, the human decision record, and outbox publications, all marked `published` when the relay is running.
2. Click **Use for replay** on a dead letter, then **Replay stored bytes**. On Windows this runs the CLI; on Linux and macOS it shows `spawn py ENOENT` (gap 5). Use `soc-ingest replay` there.

---

## 8. Metrics and alert rules

```bash
curl -s localhost:8000/metrics | grep -E '^(agent_runs_total|drafts_generated_total|draft_approvals_total|dead_letters_total)'
```

Open Prometheus at <http://localhost:9090>:

- **Status → Targets**: `soc-api` and `soc-relay` are up.
- **Graph**: `sum by (operation) (rate(search_requests_total[5m]))` while you search in the console.
- **Alerts**: ingest one more broken file and watch `DeadLettersIncreasing` go pending:

  ```bash
  printf '{"Event": {"System": ' > /tmp/broken.json
  soc-ingest ingest --tenant $T --kind windows_event --file /tmp/broken.json     # exit 2
  ```

  `AgentRunFailures` is pending while failed or refused runs from step 3 are inside its ten-minute window. A rule fires after it has been pending for five minutes.

Grafana at <http://localhost:3001> (`admin` / `admin`) has the **SOC platform** dashboard: 32 panels for API, search, pipeline, alerts and cases, agent workflows, review queue, database and Redis, and logs.

---

## Talking points

- **Custody first.** "Every alert and event here can be rebuilt from bytes we stored and hashed. Bad input is kept and labelled, not dropped."
- **Isolation in the database.** "Tenant scoping is row-level security plus composite foreign keys. The API switches into a read-only role for every request and refuses to query as the owner."
- **Agents that cannot lie quietly.** "The workflow can only read nine local tools and write templated claims. Each claim is checked against the row it cites before the draft is saved, and a person still has to decide."
- **Honest gaps.** "The API has no authentication yet and two review rules live only in the console. Those are first on the roadmap, and the README lists every gap I found."

---

## Reset

`seed_demo.py` is not idempotent. To run the demo again from scratch:

```bash
docker compose down -v && docker compose up -d --build
python demo/seed_demo.py && python demo/run_agents.py
```
