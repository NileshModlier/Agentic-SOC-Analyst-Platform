# API reference

Base URL `http://localhost:8000`. Interactive documentation is served at `/docs` (Swagger UI) and `/redoc`; the machine-readable schema is `/openapi.json` and is checked in as [`contracts/openapi.json`](../contracts/openapi.json) (OpenAPI 3.1, 26 operations, 25 paths, 65 schemas). Every example below was recorded against the demo dataset; long ids are shortened with `…`.

- [Conventions](#conventions) · [Pagination](#pagination) · [Errors](#errors)
- [Events](#events) · [Alerts](#alerts) · [Findings](#findings) · [Investigations](#investigations) · [Cases](#cases) · [Evidence](#evidence)
- [Search](#search) · [Agents](#agents) · [Operations](#operations) · [Health and metrics](#health-and-metrics)
- [Console backend-for-frontend](#console-backend-for-frontend)

```bash
T=6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14     # demo tenant, Cobalt Ridge Logistics
API=http://localhost:8000/api/v1
```

---

## Conventions

| Topic | Rule |
| --- | --- |
| Tenant | `tenant=<uuid>` is a required query parameter on every operation, including POSTs. The request runs under row-level security for that tenant only. |
| Authentication | **None.** The API trusts the `tenant` parameter. Keep it on a private network behind the console. |
| Methods | 24 `GET` operations and 2 `POST` operations (`/agent/runs`, `/agent/drafts/{id}/decisions`). There is no `PUT`, `PATCH` or `DELETE`; they return `405`. |
| Unknown parameters | Refused with `422 invalid_filter`. |
| Time | ISO 8601 with a timezone offset. `start` is inclusive, `end` exclusive, and `start` must not be after `end`. |
| Enums | `source`: `sigma_alert`, `mock_edr_alert`, `windows_event` · `severity`: `unknown`, `informational`, `low`, `medium`, `high`, `critical` · `alert_status`: `new`, `in_review`, `closed`, `suppressed` · `case_status`: `open`, `investigating`, `contained`, `recovered`, `closed` · `investigation_status`: `open`, `active`, `blocked`, `closed` · OCSF outcome: `unknown`, `success`, `failure`, `other` |
| Response headers | `X-Correlation-ID` (echoes a well-formed `X-Correlation-ID` or `X-Request-ID`, otherwise generated), `X-Trace-Id`, `X-Span-Id` |
| Raw bytes | Never returned. Evidence and operations reads return metadata and hashes only. |

## Pagination

Collections and searches return:

```json
{ "data": [ … ], "page": { "limit": 2, "has_more": true, "next_cursor": "eyJmaWx0ZXJzIjp7…" } }
```

| Parameter | Default | Rule |
| --- | --- | --- |
| `limit` | 50 | 1 to 100; `limit` echoes the requested size, not the number of rows |
| `cursor` | none | opaque, at most 4096 characters; valid only with the **same tenant, filters and limit** that produced it |

Pass `next_cursor` back as `cursor` until `has_more` is false. A cursor from another query returns `400 invalid_cursor`.

## Errors

Every error has the same envelope:

```json
{ "error": { "code": "validation_error", "message": "Request parameters are invalid.",
             "details": [ { "loc": ["tenant"], "message": "Field required" } ] } }
```

| Status | `code` | When | Recorded example |
| --- | --- | --- | --- |
| 400 | `invalid_cursor` | tampered cursor, or a cursor reused with other filters | `GET /alerts?tenant=$T&cursor=abc.def` → `Cursor is invalid for this query.` |
| 404 | `tenant_not_found` | the tenant does not exist | `GET /alerts?tenant=00000000-0000-4000-8000-000000000000` |
| 404 | `not_found` | the record does not exist in this tenant (including another tenant's record) | `GET /alerts/00000000-…?tenant=$T` → `Alert was not found.` |
| 405 | `method_not_allowed` | unsupported method | `DELETE /alerts/{id}` |
| 409 | `conflict` | deciding a draft that is not pending, or deciding twice | `Only a draft that is pending approval can be decided.` |
| 422 | `validation_error` | missing or malformed parameters or body; agent names as people | `start=2026-10-05T00:00:00` → `start must include a timezone offset`; `limit=500` → `Input should be less than or equal to 100` |
| 422 | `invalid_filter` | a parameter the operation does not accept | `GET /alerts?tenant=$T&sort=severity` → `Unknown query parameter: sort.` |
| 422 | `network_denied` | a run question that is a URL | `Investigation workflows cannot fetch a URL.` |
| 500 | `internal_error` | unexpected failure; details are logged, not returned | `The request could not be completed.` |

---

## Events

Canonical OCSF-aligned events projected from immutable source records.

### `GET /api/v1/events`

Ordered by `event_time` descending.

| Parameter | Type | Notes |
| --- | --- | --- |
| `tenant` | uuid | required |
| `source` | enum | intake source kind |
| `severity` | enum | OCSF severity |
| `event_type` | string | OCSF class name, case-sensitive, e.g. `Authentication`, `Process Activity` |
| `start`, `end` | datetime | on `event_time` |
| `limit`, `cursor` | | see [Pagination](#pagination) |

```bash
curl -s "$API/events?tenant=$T&event_type=Authentication&limit=2"
```

```json
{
  "data": [{
    "id": "4f1035f7-…", "tenant_id": "6c1f2b9e-…", "source_record_id": "b236a546-…",
    "source": "windows_event", "event_time": "2026-10-08T09:00:27Z",
    "category_uid": 3, "category_name": "Identity & Access Management",
    "class_uid": 3002, "class_name": "Authentication", "activity_id": 1, "activity_name": "Logon",
    "type_uid": 300201, "severity": "informational", "outcome": "success",
    "hostname": "HR-LT-03", "username": "CRL\\j.lindqvist",
    "message": "User CRL\\j.lindqvist logged on (logon type 2) from HR-LT-03",
    "technique_ids": [], "schema_version": "1.5.0", "normalizer_version": "1",
    "projection_generation": 1, "created_at": "2026-10-14T05:57:14.011854Z", "updated_at": "2026-10-14T05:57:14.011854Z"
  }, { "…": "…" }],
  "page": { "limit": 2, "has_more": true, "next_cursor": "eyJ…" }
}
```

### `GET /api/v1/events/{event_id}`

The summary fields above plus `document`, the full canonical OCSF document:

```json
{
  "id": "c9467d64-…", "class_name": "Process Activity", "type_uid": 100701, "severity": "informational",
  "technique_ids": ["T1059.001", "T1566.001"], "projection_generation": 2,
  "document": {
    "class_uid": 1007, "activity_id": 1, "type_uid": 100701, "type_name": "Process Activity: Launch",
    "time": 1791191642118, "status": "success", "status_id": 1,
    "user":   { "name": "CRL\\m.okafor", "domain": null, "uid": null },
    "device": { "hostname": "FIN-LT-07", "os_name": "Windows", "ip": null, "uid": null, "domain": null },
    "process": {
      "pid": 7412, "name": "powershell.exe",
      "path": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
      "cmd_line": "powershell.exe -nop -w hidden -enc UwB0AGEA…",
      "hashes": [{ "algorithm": "SHA-256", "algorithm_id": 3, "value": "9f2c6a1e…" }],
      "parent_process": { "pid": 6120, "name": "WINWORD.EXE", "cmd_line": "\"WINWORD.EXE\" /n \"C:\\Users\\m.okafor\\Downloads\\Invoice_Q3_2026.docm\"" }
    },
    "attacks": [
      { "technique": { "uid": "T1059.001", "name": null }, "tactic": null },
      { "technique": { "uid": "T1566.001", "name": null }, "tactic": null },
      { "technique": null, "tactic": { "uid": null, "name": "execution" } },
      { "technique": null, "tactic": { "uid": null, "name": "initial_access" } }
    ],
    "observables": [{ "type": "user", "value": "CRL\\m.okafor" }, { "type": "hostname", "value": "FIN-LT-07" }, "…"],
    "metadata": { "version": "1.5.0", "uid": "c9467d64-…", "original_time": "2026-10-05T09:14:02.118Z",
                  "product": { "name": "Microsoft-Windows-Sysmon", "vendor_name": "Microsoft", "feature": { "name": "1", "uid": "552301" } },
                  "profiles": ["host", "security_control"] },
    "unmapped": { "event_id": 1, "channel": "Microsoft-Windows-Sysmon/Operational", "record_id": "552301",
                  "sigma_rule_id": "438025f9-5856-4663-83f7-52f878a70a50", "fields": { "…": "…" } },
    "soc": { "source_kind": "sigma_alert", "source_record_id": "e701b2d4-…", "content_sha256": "ba7d48d3…", "normalizer_version": "1" }
  }
}
```

---

## Alerts

Vendor or rule detections. This API never changes an alert's status.

### `GET /api/v1/alerts`

Ordered by `detected_at` descending. Filters: `source`, `severity`, `alert_status`, `start`, `end` (on `detected_at`), `limit`, `cursor`.

### `GET /api/v1/alerts/{alert_id}`

```bash
curl -s "$API/alerts/ea57ccdd-466f-4224-b022-b61e9de2b578?tenant=$T"
```

```json
{
  "id": "ea57ccdd-…", "tenant_id": "6c1f2b9e-…", "source_record_id": "e701b2d4-…", "canonical_event_id": "c9467d64-…",
  "source": "sigma_alert", "external_id": "sig-20261005-0001",
  "title": "Office Application Spawning PowerShell",
  "description": "WINWORD.EXE started powershell.exe with an encoded command (T1059.001 after T1566.001).",
  "severity": "high", "status": "in_review",
  "rule_id": "438025f9-5856-4663-83f7-52f878a70a50", "rule_name": "Office Application Spawning PowerShell",
  "vendor": "Sigma", "product": "windows",
  "technique_ids": ["T1059.001", "T1566.001"], "tactics": ["execution", "initial_access"],
  "dedup_key": "ba7d48d3…",
  "correlation_key": "sigma:438025f9-5856-4663-83f7-52f878a70a50:FIN-LT-07:CRL\\m.okafor",
  "detected_at": "2026-10-05T09:14:03Z", "projection_generation": 2,
  "created_at": "2026-10-14T05:56:49.072767Z", "updated_at": "2026-10-14T05:57:30.098311Z"
}
```

`projection_generation: 2` shows the alert was replayed once; its `in_review` status survived the replay.

---

## Findings

Analyst or platform conclusions. A finding groups alerts; it is not an alert.

### `GET /api/v1/findings`

Ordered by `created_at` descending. Filters: `severity`, `start`, `end`, `limit`, `cursor`.

### `GET /api/v1/findings/{finding_id}`

Adds `alert_ids` (oldest link first).

```json
{
  "id": "326cbe85-…", "case_id": "ac35d1a3-…", "investigation_id": "295f3462-…",
  "title": "Macro document executed encoded PowerShell",
  "summary": "Sysmon, the Sigma match, and the EDR alert agree on WINWORD.EXE as the parent of powershell.exe.",
  "severity": "high", "confidence": 85, "status": "open", "disposition": null,
  "technique_ids": ["T1566.001", "T1059.001"], "tactics": ["initial_access", "execution"],
  "created_by": "Ana Torres", "created_at": "2026-10-06T11:40:00Z", "updated_at": "…",
  "alert_ids": ["ea57ccdd-…"]
}
```

`status` is one of `draft`, `open`, `accepted`, `rejected`, `superseded`; `confidence` is 0 to 100 or null.

---

## Investigations

### `GET /api/v1/investigations`

Ordered by `opened_at` descending. Filters: `investigation_status`, `start`, `end`, `limit`, `cursor`.

### `GET /api/v1/investigations/{investigation_id}`

Adds `alert_ids` (oldest link first).

```json
{
  "id": "295f3462-…", "case_id": "ac35d1a3-…",
  "title": "Initial access through Invoice_Q3_2026.docm on FIN-LT-07",
  "status": "active", "priority": "p1",
  "hypothesis": "The macro launched encoded PowerShell that beaconed to cdn-sync.example.",
  "summary": null, "assignee": "Ana Torres",
  "opened_at": "2026-10-05T10:05:00Z", "closed_at": null, "created_at": "…", "updated_at": "…",
  "alert_ids": ["ea57ccdd-…", "a859f3c1-…", "a3be4d74-…"]
}
```

---

## Cases

### `GET /api/v1/cases`

Ordered by `opened_at` descending. Filters: `severity`, `case_status`, `start`, `end`, `limit`, `cursor`.

### `GET /api/v1/cases/{case_id}`

Adds `investigation_ids` (oldest opened first) and `finding_ids` (oldest created first).

```json
{
  "id": "ac35d1a3-…", "title": "INC-0412 Finance laptop compromise and data staging",
  "description": "Macro document on FIN-LT-07 led to credential theft, PsExec to FS-02, and an archive sent to 198.51.100.23.",
  "status": "open", "severity": "critical", "assignee": "Ana Torres", "external_ref": "INC-0412",
  "opened_at": "2026-10-06T08:30:00Z", "closed_at": null,
  "investigation_ids": ["295f3462-…", "71b14aba-…", "673f4ff2-…"],
  "finding_ids": ["326cbe85-…", "72e83075-…"]
}
```

---

## Evidence

Custody records. Raw source bytes are never returned.

### `GET /api/v1/evidence`

Ordered by `collected_at` descending. Filters: `source`, `start`, `end`, `limit`, `cursor`.

### `GET /api/v1/evidence/{evidence_id}`

Adds `links` to alerts, events, findings, investigations and cases.

```json
{
  "id": "cf59568c-…", "source_record_id": "e701b2d4-…", "source": "sigma_alert",
  "evidence_type": "raw_payload", "description": "Raw sigma_alert intake",
  "content_sha256": "ba7d48d3f66bb5f2ad7f43204d09b9a2b2f0878dc65bf82b06127b662b652ec3",
  "byte_size": 1616, "collected_at": "…", "collected_by": "ingest", "created_at": "…",
  "links": [
    { "id": "1d5d413a-…", "alert_id": "ea57ccdd-…", "canonical_event_id": "c9467d64-…",
      "finding_id": null, "investigation_id": null, "case_id": null, "linked_by": "ingest", "linked_at": "…" },
    { "id": "4ecb8bbc-…", "alert_id": null, "canonical_event_id": null, "finding_id": null,
      "investigation_id": "295f3462-…", "case_id": "ac35d1a3-…", "linked_by": "Ana Torres", "linked_at": "…" }
  ]
}
```

---

## Search

PostgreSQL full-text search with the `simple` configuration. Words in `q` are required together, and punctuation in IPs, paths and process names is folded before matching, so `203.0.113.45` and `powershell.exe` match exactly. `q` is at most 256 characters; a query made only of punctuation matches nothing.

Shared filters: `q`, `source`, `severity`, `event_type`, `start`, `end`, plus `limit` and `cursor` on paged searches. `sort` is `event_time` (default), `created_time` or `severity` (highest first).

> **Known issue.** Each hit has a `headline` field. Because of unquoted empty selectors in `ts_headline` options, it currently comes back as `",StopSel=<token></b>"` instead of a snippet. Ignore it until the fix in README gap 3 lands.

### `GET /api/v1/search/events`

Searches user, host, IP, process name, path and command line, parent process, file name and path, event message and Sigma rule id. `status` is the OCSF outcome.

```bash
curl -s "$API/search/events?tenant=$T&q=svc_backup&event_type=Authentication&status=failure"
```

```json
{
  "data": [{
    "id": "89dd9350-…", "tenant_id": "6c1f2b9e-…", "source": "windows_event",
    "event_type": "Authentication", "severity": "medium", "status": "failure",
    "hostname": "DC-01", "username": "CRL\\svc_backup",
    "message": "User CRL\\svc_backup failed to log on (logon type 3) from 10.40.12.57",
    "event_time": "2026-10-06T02:31:24.553000Z", "created_at": "…", "headline": ",StopSel=svcbackup</b>"
  }, "… 3 more"],
  "page": { "limit": 50, "has_more": false, "next_cursor": null }
}
```

### `GET /api/v1/search/alerts`

Searches alert title, rule name and id, description, and the linked event's text. `status` is the alert workflow status; the `event_time` sort means detection time. Technique ids are matched only when they appear in that text (README gap 4).

```bash
curl -s "$API/search/alerts?tenant=$T&q=203.0.113.45"
```

```json
{
  "data": [{
    "id": "a3be4d74-…", "canonical_event_id": "24a903ca-…", "source": "mock_edr_alert",
    "title": "Beaconing to rare external host", "severity": "high", "status": "in_review",
    "rule_id": "edr-7f3a-0002", "rule_name": "Beaconing to rare external host",
    "event_type": "Network Activity", "hostname": "FIN-LT-07", "username": null,
    "detected_at": "2026-10-05T09:20:00Z", "created_at": "…", "headline": ",StopSel=203011345</b>"
  }],
  "page": { "limit": 50, "has_more": false, "next_cursor": null }
}
```

### `GET /api/v1/search/entities`

One result model for users, hosts, processes, files and IP addresses. `q` matches the entity value; `entity_type` narrows the type; `source`, `severity`, `status`, `event_type`, `start` and `end` keep entities linked to at least one matching event. Sort `event_time` means last seen, `created_time` first seen, `severity` the highest linked severity.

```bash
curl -s "$API/search/entities?tenant=$T&entity_type=ip&sort=severity"
```

```json
{
  "data": [
    { "id": "957c1ead-…", "entity_type": "ip", "value": "10.40.12.57", "display_value": "10.40.12.57",
      "severity": "critical", "first_seen": "2026-10-05T09:14:05Z", "last_seen": "2026-10-06T02:33:48.102000Z",
      "event_count": 9, "headline": null },
    { "id": "b3844910-…", "entity_type": "ip", "value": "203.0.113.45", "display_value": "203.0.113.45",
      "severity": "high", "first_seen": "2026-10-05T09:14:31.902000Z", "last_seen": "2026-10-05T09:20:00Z",
      "event_count": 2, "headline": null }
  ],
  "page": { "limit": 50, "has_more": true, "next_cursor": "eyJ…" }
}
```

### `GET /api/v1/search/entities/{entity_id}`

One catalogue row, same shape as a hit. Related events are a separate search, for example `search/events?q=<value>`.

### `GET /api/v1/search/facets`

Counts over the **event** corpus. Accepts `q`, `source`, `severity`, `status`, `event_type`, `start`, `end`. `event_type`, `severity` and `source` buckets each ignore their own filter; `host` and `user` return the 20 largest buckets. Not paginated.

```bash
curl -s "$API/search/facets?tenant=$T&q=svc_backup"
```

```json
{
  "event_type": [{ "value": "Authentication", "count": 5 }, { "value": "Process Activity", "count": 4 },
                 { "value": "Event Log Activity", "count": 2 }, { "value": "File System Activity", "count": 1 },
                 { "value": "Network Activity", "count": 1 }],
  "severity":   [{ "value": "informational", "count": 6 }, { "value": "medium", "count": 5 }, { "value": "high", "count": 2 }],
  "source":     [{ "value": "windows_event", "count": 11 }, { "value": "mock_edr_alert", "count": 1 }, { "value": "sigma_alert", "count": 1 }],
  "host":       [{ "value": "FS-02", "count": 9 }, { "value": "DC-01", "count": 4 }],
  "user":       [{ "value": "CRL\\svc_backup", "count": 13 }]
}
```

---

## Agents

Investigation runs and cited drafts. Runs and decisions execute as the `soc_agent` database role, which can write only the workspace tables. Drafts are never a source of truth, and approval never changes alerts, events, findings, cases, investigations or evidence.

### `POST /api/v1/agent/runs` → `201`

Starts the workflow and returns when it finishes (in the demo, under 200 ms).

| Body field | Type | Rule |
| --- | --- | --- |
| `alert_id` | uuid, optional | investigate a stored alert |
| `question` | string, optional | at most 256 characters; searched against alerts, events and entities |
| `requested_by` | string, required | 1 to 256 characters; a person, not `supervisor`, `triage`, `entity`, `threat`, `reporting`, `agent`, `system`, `soc_agent` or `soc_reader` |

One of `alert_id` or `question` is required. With both, triage and threat work from the alert, and the question is used only if the alert yields no entity lookups. Extra fields are refused.

```bash
curl -s -X POST "$API/agent/runs?tenant=$T" -H 'content-type: application/json' \
  -d '{"alert_id": "ea57ccdd-466f-4224-b022-b61e9de2b578", "requested_by": "Ana Torres"}'
```

```json
{
  "id": "fa326900-…", "tenant_id": "6c1f2b9e-…", "alert_id": "ea57ccdd-…", "question": null,
  "status": "completed", "error_code": null, "error_message": null, "requested_by": "Ana Torres",
  "created_at": "2026-10-14T05:57:43.831421Z", "finished_at": "2026-10-14T05:57:44.013114Z",
  "draft": {
    "id": "485f74ef-…", "run_id": "fa326900-…", "status": "pending_approval",
    "title": "Draft: Office Application Spawning PowerShell", "severity": "critical",
    "summary": "Stored alert ea57ccdd-… is titled Office Application Spawning PowerShell with severity high and status in_review.\n…",
    "source_of_truth": false,
    "notice": "This draft is not a source of truth. Approval records a human decision and does not change alerts, events, findings, cases, investigations, or evidence.",
    "claims": [
      { "position": 0, "template": "alert.summary",
        "statement": "Stored alert ea57ccdd-… is titled Office Application Spawning PowerShell with severity high and status in_review.",
        "arguments": { "title": "Office Application Spawning PowerShell", "status": "in_review", "severity": "high" },
        "citations": [{ "kind": "alert", "record_id": "ea57ccdd-…" }] },
      { "position": 1, "template": "alert.technique",
        "statement": "Stored alert ea57ccdd-… records technique T1059.001.",
        "arguments": { "technique": "T1059.001" }, "citations": [{ "kind": "alert", "record_id": "ea57ccdd-…" }] },
      "… 7 more: technique T1566.001, the event, the evidence, the user, the host and two processes"
    ],
    "approval": null, "created_at": "…", "updated_at": "…"
  },
  "memory": [
    { "sequence": 1, "agent": "supervisor", "kind": "plan", "payload": { "plan": ["triage", "entity", "threat", "reporting"] } },
    { "sequence": 2, "agent": "triage", "kind": "observation",
      "payload": { "tool": "get_alert", "arguments": { "alert_id": "ea57ccdd-…" }, "error": null,
                   "records": [{ "kind": "alert", "id": "ea57ccdd-…", "fields": { "title": "…", "severity": "high", "status": "in_review",
                                 "technique_ids": ["T1059.001", "T1566.001"], "rule_id": "438025f9-…", "canonical_event_id": "c9467d64-…" } }] } },
    "… sequences 3 to 14: get_event, list_alert_evidence, triage claims, entity lookups, threat searches",
    { "sequence": 15, "agent": "reporting", "kind": "observation",
      "payload": { "draft_id": "485f74ef-…", "status": "pending_approval", "claims": 9, "rejected": 0 } }
  ]
}
```

The draft's severity is the highest across its claims. Here an entity claim (`CRL\m.okafor`, highest severity critical) lifts a `high` alert to a `critical` draft.

| Outcome | HTTP | Run `status` | Draft `status` | Recorded in the demo |
| --- | :-: | --- | --- | --- |
| Every claim matches its record | 201 | `completed` | `pending_approval` | alert runs, `question: "svc_backup"` (18 claims) |
| Nothing citable | 201 | `completed` | `insufficient_evidence` | `question: "mimikatz"` |
| A claim does not match its record | 201 | `failed` (`validation_failed`) | `validation_failed` | covered by tests |
| Unknown alert | 201 | `failed` (`alert_not_found`) | none | random alert id |
| Question is a URL | 422 `network_denied` | not stored | | `https://intel.example/ioc/203.0.113.45` |
| Agent name as `requested_by` | 422 `validation_error` | not stored | | `"triage"` |
| Neither `alert_id` nor `question` | 422 `validation_error` | not stored | | `alert_id or question is required` |

### `GET /api/v1/agent/runs`

Newest first, with a draft summary when reporting stored one. Filters: `run_status` (`running`, `completed`, `failed`), `draft_status`, `alert_id`, `start`, `end`, `limit`, `cursor`. Each item has the run fields plus `draft_id`, `draft_status`, `draft_title`, `draft_severity`.

### `GET /api/v1/agent/runs/{run_id}`

The same shape as the POST response: the run, its full memory in sequence order, and the draft.

### `GET /api/v1/agent/drafts`

Newest first. Filters: `status` (`pending_approval`, `approved`, `rejected`, `insufficient_evidence`, `validation_failed`), `start`, `end`, `limit`, `cursor`. Items carry `id`, `run_id`, `status`, `title`, `summary`, `severity`, `source_of_truth: false`, `approval` and timestamps, without claims.

### `GET /api/v1/agent/drafts/{draft_id}`

The full draft with claims, citations, notice and approval.

### `POST /api/v1/agent/drafts/{draft_id}/decisions` → `200`

| Body field | Type | Rule |
| --- | --- | --- |
| `decision` | `approved` or `rejected` | required |
| `actor` | string | required, a person (same reserved names as `requested_by`) |
| `note` | string, optional | at most 2000 characters; blank becomes null |

```bash
curl -s -X POST "$API/agent/drafts/485f74ef-…/decisions?tenant=$T" -H 'content-type: application/json' \
  -d '{"decision": "approved", "actor": "Ben Clarke", "note": "Claims match the stored alert, event, and evidence."}'
```

Returns the draft with `status: "approved"` and:

```json
"approval": { "decision": "approved", "actor": "Ben Clarke",
              "note": "Claims match the stored alert, event, and evidence.", "created_at": "…" }
```

A second decision returns `409 conflict`. Neither the reviewer role nor requester ≠ decider is checked here; the console enforces both (README gap 2).

---

## Operations

Intake health for the tenant. Payload bytes and outbox payloads are never returned.

### `GET /api/v1/operations/connectors`

One row per source kind, not paginated.

```json
{ "data": [
  { "source": "sigma_alert",    "label": "Sigma",   "projected": 5,  "dead_lettered": 1, "last_received_at": "…" },
  { "source": "mock_edr_alert", "label": "EDR",     "projected": 6,  "dead_lettered": 1, "last_received_at": "…" },
  { "source": "windows_event",  "label": "Windows", "projected": 19, "dead_lettered": 2, "last_received_at": "…" }
] }
```

Counts are receipts by their latest status; `last_received_at` is the intake time, not the event time.

### `GET /api/v1/operations/dead-letters`

Newest first. Filters: `open_only` (boolean; only those replay has not resolved), `start`, `end`, `limit`, `cursor`.

```json
{ "data": [
  { "id": "000d3468-…", "source_record_id": "fc8387dc-…", "outbox_event_id": null,
    "stage": "replay", "reason_code": "invalid_json", "error_message": "payload is not valid JSON",
    "attempt_count": 2, "payload_sha256": null, "created_at": "…", "resolved_at": null },
  { "id": "7f0c0cd8-…", "stage": "parse", "reason_code": "missing_timestamp", "error_message": "missing TimeCreated", "attempt_count": 1, "…": "…" }
], "page": { "limit": 50, "has_more": false, "next_cursor": null } }
```

`stage` is `parse`, `replay` or `publish`.

### `GET /api/v1/operations/publications`

Outbox rows, newest first. Filters: `start`, `end`, `limit`, `cursor`.

```json
{ "id": "5cdfeba5-…", "aggregate_type": "source_record", "aggregate_id": "fc8387dc-…",
  "event_type": "ingest.replay_failed", "status": "published", "attempts": 0, "last_error": null,
  "created_at": "2026-10-14T05:57:31.221946Z", "published_at": "2026-10-14T05:57:37.542697Z" }
```

`status` is `pending`, `published` or `dead_lettered`.

---

## Health and metrics

Not part of the OpenAPI schema and not tenant-scoped.

| Route | Response |
| --- | --- |
| `GET /health` | `200 {"status": "ok"}` |
| `GET /ready` | `200 {"status": "ok", "postgres": "ok", "redis": "ok"}`, or `503` with the failing component marked `unavailable` |
| `GET /metrics` | Prometheus text format; `404` when `SOC_METRICS_ENABLED=false` |

---

## Console backend-for-frontend

The console calls the API through its own routes on port 3000. These are what a browser sees.

| Route | Method | Rule |
| --- | --- | --- |
| `/api/auth/login` | POST `{operator, password, tenantId}` | sets the `soc_session` cookie (12 hours); `401 unauthenticated` on a bad operator, password or tenant format |
| `/api/auth/logout` | POST | clears the cookie |
| `/api/platform/<api path>` | GET, POST | needs a session (`401`); forwards to `SOC_API_URL`, replacing any `tenant` with the session's; `502 api_unreachable` when the API is down |
| `/api/platform/api/v1/agent/runs` | POST `{alert_id?, question?}` | `requested_by` is set to the signed-in operator's name |
| `/api/platform/api/v1/agent/drafts/{id}/decisions` | POST `{decision, note?, intent?}` | reviewer or admin only (`403`); the run's requester cannot decide (`403`); reject and `intent: "request_changes"` need a note (`422`); `request_changes` is sent as `rejected` with the note prefixed `[changes-requested]` |
| `/api/operations/replay` | POST `{sourceRecordId}` | admin only; runs the replay CLI through `py -3` (Windows only) |
