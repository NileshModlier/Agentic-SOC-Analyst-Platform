<div align="center">

# Agentic SOC Analyst Platform

**Evidence-first security operations. Raw detections are kept byte for byte, normalised to OCSF, searched in PostgreSQL, and investigated by a LangGraph workflow whose every claim is checked against a stored record before a person decides.**

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?logo=fastapi&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-1.x-1C3C3C)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%C2%B7%20RLS%20%C2%B7%20FTS-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7%20Streams-DC382D?logo=redis&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![OCSF](https://img.shields.io/badge/OCSF-1.5%20subset-5A45FF)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-traces-425CC7?logo=opentelemetry&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-31%20metric%20families%20%C2%B7%2010%20rules-E6522C?logo=prometheus&logoColor=white)
![Tests](https://img.shields.io/badge/tests-57%20passing-2ea44f)

<img src="docs/screenshots/demo-walkthrough.gif" width="900" alt="Walkthrough: sign in, dashboard, IP search, alert detail, an investigation run, a reviewer's approval, separation of duties and the administration page">

<sub>Recorded from this repository running locally against the bundled demo dataset (fictional tenant).</sub>

</div>

---

## Contents

1. [What it is](#what-it-is)
2. [Design principles](#design-principles)
3. [Highlights](#highlights)
4. [Screenshots](#screenshots)
5. [Architecture overview](#architecture-overview)
6. [Feature matrix](#feature-matrix)
7. [Tech stack](#tech-stack)
8. [Setup guide](#setup-guide)
9. [API documentation](#api-documentation)
10. [Demo walkthrough](#demo-walkthrough)
11. [Project structure](#project-structure)
12. [Testing](#testing)
13. [Security model](#security-model)
14. [Observability](#observability)
15. [Known gaps and roadmap](#known-gaps-and-roadmap)
16. [Documentation index](#documentation-index)

---

## What it is

A multi-tenant platform for a security operations centre (SOC), built in six phases:

| Phase | What it added |
| --- | --- |
| 1 · Intake | Immutable raw storage of Sigma, EDR and Windows payloads; OCSF-aligned events; alerts, evidence, dead letters, replay; a transactional outbox to Redis Streams |
| 2 · Read API | A tenant-scoped, read-only FastAPI service with keyset pagination and a stable error envelope |
| 3 · Search | PostgreSQL full-text search over events, alerts and an entity catalogue, with facets |
| 4 · Agents | A LangGraph investigation workflow that drafts cited claims, plus a human approval gate |
| 5 · Console | A Next.js security operations console with role gates and a page guide called Sentinel |
| 6 · Observability | JSON logs, OpenTelemetry traces, Prometheus metrics, health probes, Grafana, Loki, Tempo and alert rules |

The "agents" are deterministic. There is **no language model in the loop today**: the specialists call nine local database tools and fill six fixed claim templates. The design leaves a clear seat for a model later (see [roadmap](#known-gaps-and-roadmap)), but nothing in this repository calls one.

## Design principles

| Principle | How the code enforces it |
| --- | --- |
| **Raw bytes are the source of truth** | Every payload is stored once per tenant under its SHA-256 in `source_records`. A trigger rejects `UPDATE` and `DELETE`, and a check constraint recomputes the hash with `pgcrypto`. Every derived row can be rebuilt by **replay**. |
| **Bad input is kept, not dropped** | Unparseable bytes are still stored, then **dead-lettered** with a reason code such as `invalid_json`, `invalid_xml`, `schema_mismatch` or `missing_timestamp`. |
| **Tenants cannot see each other** | Composite `(tenant_id, id)` foreign keys on every child table, row-level security on all 24 tables, and `SET LOCAL ROLE` into a tenant-scoped role on every request. |
| **Agents are not a source of truth** | Claims come from six templates filled with stored fields. The reporting agent **reloads every cited row** and stores the draft as `validation_failed` if any argument differs. `source_of_truth = false` is a database check constraint. |
| **People decide** | Only a `pending_approval` draft can be decided, once. Agent names are refused as actors. Approval writes a decision row and never turns the draft into a finding. |
| **No network from the workflow** | The tool registry is a closed set of nine database reads. A URL-shaped question or tool argument raises `network_denied`, and a test asserts the agent package imports no HTTP or socket client. |

## Highlights

- 🧾 **One-transaction intake.** The immutable bytes, the OCSF event, the alert, the evidence record and its links, the search rows, the receipt and an outbox row are written together. Identical bytes deduplicate per tenant; a rollback discards all of it.
- 🪟 **Real-world formats.** Sigma rule-match JSON (the matched Windows event becomes the canonical activity), a mock EDR alert format, and Windows events as **Event XML in UTF-8 or UTF-16, Event JSON, or Winlogbeat JSON**. Fifteen Security, System and Sysmon event IDs map to eight OCSF classes; Sigma and EDR detections without an activity become Detection Findings.
- ♻️ **Replay and dead letters.** `soc-ingest replay` re-parses stored bytes, increments `projection_generation`, keeps the analyst-owned alert status, and resolves open dead letters when it succeeds.
- 📬 **Transactional outbox to Redis Streams.** The relay claims rows with `FOR UPDATE SKIP LOCKED`, delivers at least once, backs off exponentially up to 60 seconds, and dead-letters with `publish_exhausted` after five attempts.
- 🔎 **PostgreSQL-native search.** Full-text search over events, alerts and five entity types. IPs, paths and process names fold to one token, so `203.0.113.45` and `powershell.exe` match exactly. Facets leave out their own filter. Cursors are HMAC-signed and bound to tenant, filters and page size.
- 🤖 **LangGraph investigation workflow.** A supervisor routes triage, entity, threat and reporting agents. Every tool call and claim proposal is written to append-only run memory. A run ends as `pending_approval`, `insufficient_evidence`, `validation_failed`, or a failed run that invents nothing.
- ✅ **Human approval with separation of duties.** In the console only reviewers decide, the requester of a run cannot decide its draft, and "request changes" is stored as a rejection with a marked note.
- 🖥️ **Security operations console.** Next.js 15 and React 19: dashboard, alert explorer with facets, entity explorer, cases, investigation timelines, agent workspace, review queue and administration, with a built-in page guide.
- 📡 **Operable from day one.** Correlated JSON logs, OpenTelemetry spans for HTTP, search, intake, outbox and each agent node, **31 Prometheus metric families**, `/health` and `/ready`, a provisioned 32-panel Grafana dashboard and 10 alert rules.

---

## Screenshots

> Captured from this repository's API, console and Prometheus running locally against the demo dataset in [`demo/`](demo): a fictional company, **Cobalt Ridge Logistics**, with a five-day intrusion told through 34 raw payloads (4 of them broken on purpose). External addresses use the RFC 5737 documentation ranges.

| | |
| :-: | :-: |
| ![Dashboard](docs/screenshots/02-dashboard.png) **Dashboard.** Open and high-severity alerts, active cases, pending reviews, alert trend, severity and host facets | ![Alert explorer](docs/screenshots/03-alert-explorer.png) **Alert explorer.** Full-text search, filters, and event-corpus facets for severity, source, OCSF class, host and user |
| ![Agent workspace](docs/screenshots/11-agent-workspace.png) **Agent workspace.** No chat box. One click runs the workflow; each claim cites one stored record and the run memory is shown in order | ![Review queue](docs/screenshots/12-review-queue.png) **Review queue.** A reviewer reads each claim and its citation, then approves, rejects, or requests changes |
| ![Investigation timeline](docs/screenshots/10-investigation-timeline.png) **Investigation timeline.** Linked alerts and the agent runs for them, in time order | ![Self-approval blocked](docs/screenshots/12c-review-self-approval-blocked.png) **Separation of duties.** The person who requested a run cannot decide its draft |
| ![Alert detail](docs/screenshots/04-alert-detail.png) **Alert detail.** The stored detection beside its canonical OCSF event | ![Administration](docs/screenshots/13-administration.png) **Administration.** Connector health, dead letters with reason codes, human decisions and outbox publications |

<details>
<summary><b>More screens</b>: sign-in, IP search, entities, cases, failure states, page guide, API docs, Prometheus</summary>

| | |
| :-: | :-: |
| ![Login](docs/screenshots/01-login.png) Tenant sign-in with local operators | ![IP search](docs/screenshots/03b-alert-search-ip.png) Searching `203.0.113.45` finds the beaconing alert |
| ![Entities](docs/screenshots/05-entities.png) Entity explorer, hosts | ![Entity detail](docs/screenshots/06-entity-detail.png) `CRL\svc_backup`: related alerts and 13 linked events |
| ![Cases](docs/screenshots/07-cases.png) Case management | ![Case detail](docs/screenshots/08-case-detail.png) Case with investigations and findings (shows gap 10) |
| ![Investigations](docs/screenshots/09-investigations.png) Investigations | ![Approved](docs/screenshots/12b-review-approved.png) After approval: the decision record |
| ![Insufficient evidence](docs/screenshots/11b-agent-workspace-insufficient.png) A question with no matching records ends `insufficient_evidence` | ![Failed run](docs/screenshots/11c-agent-workspace-failed.png) An unknown alert id fails as `alert_not_found` and stores no draft |
| ![Sentinel](docs/screenshots/14-sentinel-guide.png) Sentinel page guide, light appearance | ![Replay](docs/screenshots/13b-admin-replay.png) Console replay on Linux fails with `spawn py ENOENT` (gap 5) |
| ![OpenAPI](docs/screenshots/15-openapi-docs.png) FastAPI `/docs` | ![Search contract](docs/screenshots/15b-openapi-search-alerts.png) `GET /api/v1/search/alerts` parameters |
| ![Targets](docs/screenshots/16-prometheus-targets.png) Prometheus scraping the API and relay | ![Rules](docs/screenshots/17-prometheus-alerts.png) The 10 alert rules; two pending after a dead letter and a failed run |
| ![Search rate](docs/screenshots/18-prometheus-search-rate.png) `sum by (operation) (rate(search_requests_total[5m]))` | |

</details>

A captioned gallery is in **[docs/SCREENSHOTS.md](docs/SCREENSHOTS.md)**.

---

## Architecture overview

```mermaid
flowchart LR
  subgraph SRC[Raw intake]
    direction TB
    S1[Sigma rule-match JSON]
    S2[Mock EDR alert JSON]
    S3[Windows Event XML · JSON · Winlogbeat]
  end

  subgraph ING[soc-ingest · one transaction]
    direction TB
    I1[size and tenant checks] --> I2[SHA-256 dedupe<br/>immutable source_records]
    I2 --> I3{parser}
    I3 -->|parsed| I4[canonical_events · alerts<br/>evidence · search rows]
    I3 -->|parse error| I5[dead_letters]
    I4 --> I6[outbox_events]
    I5 --> I6
  end

  DB[(PostgreSQL 16<br/>24 tables · RLS on all)]

  subgraph API[soc-api · FastAPI :8000]
    direction TB
    A1[read and search routes<br/>role soc_reader]
    A2[LangGraph workflow<br/>role soc_agent]
    A3[operations routes]
  end

  subgraph CON[console · Next.js :3000]
    direction TB
    C1[pages and Sentinel guide] --> C2[BFF proxy<br/>signed session · role gates]
  end

  SRC --> ING --> DB
  C2 -->|tenant from the session| API
  API --> DB
  DB --> RELAY[soc-outbox-relay :9101] -->|XADD soc.outbox| RS[(Redis Streams)]
```

Every process writes JSON logs, OTLP traces and Prometheus metrics; Compose wires them to Loki, Tempo, Prometheus, Alertmanager and Grafana (see [Observability](#observability)).

**Processes.** `soc-ingest` is an operator CLI that stores, parses and projects in one transaction. `soc-outbox-relay` moves outbox rows into a Redis Stream. `soc-api` serves read, search, operations and agent routes, and runs the LangGraph workflow in-process. `console/` is a separate Next.js app that acts as a backend-for-frontend. PostgreSQL is the system of record for everything; Redis is used only by the relay and by the readiness and metrics probes, never for search or agents.

**Investigation workflow.**

```mermaid
flowchart LR
  START((start)) --> SUP[supervisor<br/>writes the plan]
  SUP -->|cursor 0| TRI[triage<br/>get_alert · get_event · list_alert_evidence<br/>or search_alerts + search_events]
  TRI --> SUP
  SUP -->|cursor 1| ENT[entity<br/>event_entity_keys · get_entity_by_value<br/>at most 8 lookups]
  ENT --> SUP
  SUP -->|cursor 2| THR[threat<br/>search_alerts per stored technique<br/>at most 8]
  THR --> SUP
  SUP -->|cursor 3| REP[reporting<br/>reload every cited row · store draft]
  REP --> SUP
  SUP -->|cursor 4| END((end))
  SUP -->|failed| FAIL[failure] --> END
```

The full design (intake transaction, data model, OCSF mapping, roles and grants, search folding, cursor format, agent state and claim templates, console BFF, observability, and design decisions) is in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Feature matrix

| Area | Capability | Status |
| --- | --- | :-: |
| Intake | Sigma, mock EDR, Windows (XML UTF-8/UTF-16, Event JSON, Winlogbeat) parsers | ✅ |
| Intake | Immutable raw store, per-tenant SHA-256 dedupe, 8 MiB limit, tenant status checks | ✅ |
| Intake | Dead letters for parse, replay and publish failures; replay from stored bytes | ✅ |
| Normalisation | OCSF 1.5 subset: 9 classes, `type_uid`, observables, ATT&CK techniques and tactics | ✅ |
| Eventing | Transactional outbox to Redis Streams with retries, back-off and dead letters | ✅ |
| Tenancy | Composite tenant foreign keys, RLS on every table, scoped roles, column-level grants | ✅ |
| Read API | 26 operations, keyset cursors, query-parameter allow-list, one error envelope | ✅ |
| Search | Full-text search over events, alerts and entities; facets; 3 sort orders | ✅ snippet bug, gap 3 |
| Agents | Supervisor plus 4 specialists, 9 local tools, 6 claim templates, citation validation | ✅ deterministic, no LLM |
| Review | Approve, reject, request changes; reviewer role and requester ≠ decider | ⚠️ enforced in the console only |
| Casework | Cases, investigations, findings, alert and evidence links | ⚠️ read API; writes through a Python module |
| Console | 13 pages, BFF proxy, signed session, 3 roles, Sentinel guide | ✅ |
| Authentication | Local operators in the console; the API trusts a `tenant` parameter | ⚠️ demo grade |
| Observability | JSON logs, OTel traces, 31 metric families, health and readiness, Grafana, 10 alert rules | ✅ |
| Tests | 57 backend tests (30 unit, 27 integration); no console tests | ⚠️ |

The full matrix, with the file or test behind each line, is in **[docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md)**.

---

## Tech stack

| Layer | Choice |
| --- | --- |
| API | Python 3.12+, FastAPI, Pydantic v2, pydantic-settings, Uvicorn |
| Data | PostgreSQL 16 (RLS, `pgcrypto`, generated `tsvector` columns, GIN indexes), SQLAlchemy 2, Alembic (6 migrations), psycopg 3 |
| Agents | LangGraph `StateGraph`, in-process; LangSmith tracing switched off during runs |
| Messaging | Redis 7 Streams through a transactional outbox |
| Console | Next.js 15 App Router, React 19, TanStack Query 5, Recharts, Tailwind CSS 3, Radix Slot, lucide-react |
| Observability | OpenTelemetry SDK with OTLP gRPC, prometheus-client, Prometheus 2.55, Alertmanager 0.27, Grafana 11.4, Tempo 2.6, Loki and Promtail 3.3 |
| Packaging | Docker image running as uid 10001, Docker Compose with 11 services |

---

## Setup guide

**Prerequisites:** Docker with Compose v2, or PostgreSQL 16 and Redis 7 installed locally. Python 3.12+ and Node.js 20+ on the host for the CLI, the demo kit and the console.

### Quick start

```bash
# 1. PostgreSQL, Redis, migrations, the API (:8000), the outbox relay (:9101) and the observability stack
docker compose up -d --build

# 2. Python tooling on the host: CLI, demo kit, tests
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
cp .env.example .env                                      # SOC_DATABASE_URL points at localhost:5434

# 3. Demo data: two tenants, 36 payloads, a replay, casework, investigations and decisions
python demo/make_payloads.py
python demo/seed_demo.py
python demo/run_agents.py

# 4. Console on :3000
cd console
cp .env.example .env.local                                # set CONSOLE_SESSION_SECRET to a long random string
npm ci && npm run dev
```

Sign in at <http://localhost:3000/login> with tenant `6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14` as `analyst` / `analyst-local`, `reviewer` / `reviewer-local` or `admin` / `admin-local`.

| URL | What |
| --- | --- |
| <http://localhost:8000/docs> · `/redoc` · `/openapi.json` | API reference |
| <http://localhost:8000/health> · `/ready` · `/metrics` | Probes and Prometheus metrics |
| <http://localhost:3000> | Console |
| <http://localhost:3001> | Grafana (`admin` / `admin`), dashboard **SOC platform** |
| <http://localhost:9090> · <http://localhost:9093> | Prometheus · Alertmanager |

### Ingest your own data

```bash
# A tenant must exist first; there is no tenant API
psql postgresql://soc:soc@localhost:5434/soc -c \
  "INSERT INTO tenants (id, slug, name, status, created_at, updated_at)
   VALUES (gen_random_uuid(), 'acme', 'Acme', 'active', now(), now()) RETURNING id;"

soc-ingest ingest --tenant <uuid> --kind sigma_alert    --file alert.json
soc-ingest ingest --tenant <uuid> --kind mock_edr_alert --file edr.json
soc-ingest ingest --tenant <uuid> --kind windows_event  --file 4625.xml
soc-ingest replay --tenant <uuid> --source-record <source-record-uuid>
```

The CLI prints one JSON object. Exit codes: `0` projected or duplicate, `2` stored and dead-lettered, `3` rejected (unknown or disabled tenant, payload over the size limit, unknown source record on replay).

### Configuration

| Variable | Default | Used by |
| --- | --- | --- |
| `SOC_DATABASE_URL` | **required** | every process, Alembic, tests |
| `SOC_REDIS_URL` | **required** | API readiness and inventory, relay |
| `SOC_API_CURSOR_SECRET` | `dev-only-change-me` | HMAC key for list and search cursors |
| `SOC_MAX_PAYLOAD_BYTES` | `8388608` | intake size limit |
| `SOC_OUTBOX_STREAM` · `_BATCH_SIZE` · `_MAX_ATTEMPTS` · `_POLL_INTERVAL_SECONDS` | `soc.outbox` · `100` · `5` · `1` | relay |
| `SOC_SERVICE_NAME` | `soc-api` (CLI `soc-ingest`, relay `soc-relay`) | logs and traces |
| `SOC_OTLP_ENDPOINT` | empty, so no export | traces |
| `SOC_LOG_FORMAT` · `SOC_METRICS_ENABLED` · `SOC_METRICS_PORT` | `json` · `true` · `9101` | logs, `/metrics`, relay metrics server |
| `SOC_API_URL` · `CONSOLE_SESSION_SECRET` | `http://127.0.0.1:8000` · `dev-console-session` | console |

Local installs without Docker, a UTF-8 database requirement that is easy to miss, troubleshooting and a production checklist are in **[docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md)**.

---

## API documentation

Every operation requires `?tenant=<uuid>`. Lists return `{"data": [...], "page": {"limit", "has_more", "next_cursor"}}` with a default page of 50 and a maximum of 100. Unknown query parameters are refused with `422 invalid_filter`, and every error uses one envelope: `{"error": {"code", "message", "details?"}}`.

| Tag | Operations |
| --- | --- |
| **Events** | `GET /api/v1/events` · `GET /api/v1/events/{event_id}` (includes the OCSF document) |
| **Alerts** | `GET /api/v1/alerts` · `GET /api/v1/alerts/{alert_id}` |
| **Findings** | `GET /api/v1/findings` · `GET /api/v1/findings/{finding_id}` |
| **Investigations** | `GET /api/v1/investigations` · `GET /api/v1/investigations/{investigation_id}` |
| **Cases** | `GET /api/v1/cases` · `GET /api/v1/cases/{case_id}` |
| **Evidence** | `GET /api/v1/evidence` · `GET /api/v1/evidence/{evidence_id}` (custody metadata, never bytes) |
| **Search** | `GET /api/v1/search/events` · `/search/alerts` · `/search/entities` · `/search/entities/{entity_id}` · `/search/facets` |
| **Agents** | `POST /api/v1/agent/runs` · `GET /api/v1/agent/runs` · `GET /api/v1/agent/runs/{run_id}` · `GET /api/v1/agent/drafts` · `GET /api/v1/agent/drafts/{draft_id}` · `POST /api/v1/agent/drafts/{draft_id}/decisions` |
| **Operations** | `GET /api/v1/operations/connectors` · `/operations/dead-letters` · `/operations/publications` |

```bash
T=6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14

# Failed logons for the service account, newest first
curl -s "localhost:8000/api/v1/search/events?tenant=$T&q=svc_backup&event_type=Authentication&status=failure"

# Investigate a stored alert
curl -s -X POST "localhost:8000/api/v1/agent/runs?tenant=$T" -H 'content-type: application/json' \
  -d '{"alert_id": "<alert-uuid>", "requested_by": "Ana Torres"}'

# A person approves the draft
curl -s -X POST "localhost:8000/api/v1/agent/drafts/<draft-uuid>/decisions?tenant=$T" \
  -H 'content-type: application/json' -d '{"decision": "approved", "actor": "Ben Clarke", "note": "Claims match the records."}'
```

Claims in an approved draft from the demo run:

```text
Stored alert ea57ccdd-… is titled Office Application Spawning PowerShell with severity high and status in_review.
Stored alert ea57ccdd-… records technique T1059.001.
Stored event c9467d64-… is Process Activity with severity informational: Process C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe launched by CRL\m.okafor: …
Stored evidence cf59568c-… is raw_payload with sha256 ba7d48d3….
Stored user CRL\m.okafor is linked to 6 events with highest severity critical.
```

Parameters, schemas, filters, sort orders, error codes and recorded responses for every operation are in **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)**. The checked-in contract is [`contracts/openapi.json`](contracts/openapi.json), and a test fails if the application drifts from it.

---

## Demo walkthrough

| Step | Who | Where | What it shows |
| --- | --- | --- | --- |
| 1 | Operator | `soc-ingest` | 34 payloads for Cobalt Ridge: 30 projected, 4 dead-lettered with reason codes; identical bytes return `duplicate: true` |
| 2 | Operator | `soc-ingest replay` | Replay raises `projection_generation` to 2 and keeps `in_review`; replaying broken bytes adds a `replay` dead letter |
| 3 | Analyst | Dashboard, Alerts | 11 alerts and 30 events; searching `203.0.113.45` finds the beaconing alert |
| 4 | Analyst | Alert, Agent workspace | One click runs supervisor, triage, entity, threat and reporting; the draft cites the alert, event, evidence and entities |
| 5 | Analyst | Agent workspace | No matching records ends `insufficient_evidence`; an unknown alert fails `alert_not_found`; a URL is refused `network_denied` |
| 6 | Reviewer | Review queue | Approve, reject with a note, or request changes; the requester cannot decide; deciding twice is `409` |
| 7 | Admin | Administration | Connector health, open dead letters, the decision record, outbox publications |
| 8 | Anyone | Prometheus, Grafana | Search rate, agent runs, drafts and decisions; `DeadLettersIncreasing` and `AgentRunFailures` go pending |

The script, with payloads, commands, expected output and console clicks, is in **[docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md)**.

---

## Project structure

```text
├── soc_platform/
│   ├── main.py               FastAPI composition root (create_app)
│   ├── cli.py                soc-ingest: ingest | replay
│   ├── config.py             SOC_* settings
│   ├── domain/               enums, OCSF canonical document, intake errors, outbox event names
│   ├── ingestion/            codec, sigma, mock_edr, windows_event, taxonomy, registry, pipeline
│   ├── models/               24 tables (SQLAlchemy 2)
│   ├── search/               full-text folding, entity extraction, projections
│   ├── api/                  read, search, agent and operations routes; schemas; cursors; errors
│   ├── agents/               LangGraph graph, nodes, tools, citations, drafts, memory, network guard
│   ├── casework.py           create cases, investigations, findings and links (no HTTP surface)
│   ├── outbox/               publisher and relay (soc-outbox-relay)
│   └── observability/        logs, traces, metrics, inventory collector, middleware, health
├── alembic/versions/         6 migrations
├── contracts/openapi.json    checked-in API contract
├── console/                  Next.js 15 security operations console
├── deploy/observability/     Prometheus, alert rules, Alertmanager, Grafana, Tempo, Loki, Promtail
├── demo/                     payload generator, seed script, investigation and decision driver
├── tests/                    57 pytest tests
└── Dockerfile · docker-compose.yml · pyproject.toml · alembic.ini
```

---

## Testing

```bash
pytest -q                          # 57 passed; integration tests use PostgreSQL on localhost:5434
pytest -q -m "not integration"     # 30 tests; 29 need no services (see note below)
SOC_TEST_DATABASE_URL=postgresql+psycopg://soc:soc@localhost:5434/soc_test pytest -q   # an existing, separate UTF-8 database
```

Integration tests run Alembic to `head`, isolate each test, and skip cleanly when PostgreSQL is not reachable. One test outside the `integration` marker, `test_observability.py::test_health_carries_trace_headers_and_metrics_stay_out_of_openapi`, calls `/ready` and expects PostgreSQL on `localhost:5434` and Redis on `localhost:6379`; it fails rather than skips when either is down.

| Suite | Tests | Proves |
| --- | :-: | --- |
| `test_phase1.py` | 18 | Transactional intake and replay, status kept on replay, dedupe, per-tenant dedupe, dead letters, size limit, disabled tenant, immutability triggers, hash check, cross-tenant FK rejection, outbox invisible until commit, relay success, back-off and dead letter, RLS |
| `test_parsers.py` | 8 | Sigma with and without a matched event, EDR, seven-digit fractional seconds, UTF-16 XML, failed-logon outcome |
| `test_api.py` | 4 | `soc_reader` is select-only and tenant-scoped; filters, cursors and isolation; casework and evidence reads; request contract |
| `test_search.py` · `test_search_text.py` | 2 · 2 | Filters, facets, sorts and cursors; replay updates search in place; identifier folding |
| `test_agents.py` · `test_agent_workflow.py` | 7 · 2 | Templates, unknown templates, people only, URLs refused, closed tool set, agents cannot approve, no network imports; an end-to-end cited draft and decision; a tool failure never approves |
| `test_console_reads.py` | 1 | Workspace, entity and operations reads the console relies on |
| `test_observability.py` | 7 | JSON logs, correlation-ID injection refused, metrics, search observer, Redis wrapper, trace headers |
| `test_surface.py` · `test_pagination.py` · `test_openapi.py` | 2 · 3 · 1 | Only GET plus the two agent POSTs exist; cursor tamper-proofing; OpenAPI equals the checked-in contract |

Verified on Python 3.12.3 with PostgreSQL 16 and Redis 7: **57 passed in about 6 seconds**.

---

## Security model

- **Tenant isolation in the database.** RLS policies compare `tenant_id` with `current_setting('soc.tenant_id')`. Every request runs `SET LOCAL ROLE soc_reader` (or `soc_agent`) and sets `soc.tenant_id` for the transaction. Every query first checks that it runs as a scoped role, because the login role owns the tables and would bypass RLS.
- **Least privilege.** `soc_reader` can only `SELECT`, and on `source_records` only metadata columns, never `payload`. `soc_agent` can also insert and update the six workspace tables and nothing else. Dead-letter bytes and outbox payloads are excluded column by column.
- **Immutability.** Triggers reject `UPDATE` and `DELETE` on `source_records` and `evidence`. An evidence hash must equal its source record's hash. `investigation_drafts.source_of_truth = false` is a check constraint.
- **Agent containment.** The tool registry is closed. Network-shaped arguments raise `network_denied`. LangSmith tracing is forced off during a run. Actors named `supervisor`, `triage`, `entity`, `threat`, `reporting`, `agent`, `system`, `soc_agent` or `soc_reader` are refused.
- **Not production-ready yet.** The API has **no caller authentication**: it trusts the `tenant` parameter and must sit behind the console on a private network. Console operators are hard-coded local accounts. See [known gaps](#known-gaps-and-roadmap).

---

## Observability

| Signal | Implementation |
| --- | --- |
| Logs | JSON to stderr with `service`, `correlation_id`, `trace_id` and `span_id`; one access log per request; Promtail ships container logs to Loki |
| Traces | OTLP gRPC to Tempo; spans for HTTP, `search`, `ingest`, `replay`, `outbox.publish`, `redis.command`, `investigation.workflow`, `agent.node`, `draft.store` and `draft.review` |
| Correlation | `X-Correlation-ID` or `X-Request-ID` is accepted when well formed, otherwise generated; responses carry `X-Correlation-ID`, `X-Trace-Id` and `X-Span-Id` |
| Metrics | 20 process families (API, search, agents, drafts, reviews, database, Redis, outbox), 10 inventory families read from PostgreSQL on each scrape and cached for 15 seconds, and pool occupancy |
| Health | `/health` (liveness) and `/ready` (PostgreSQL and Redis; `503` when either fails) |
| Alerts | `ApiDown`, `RelayDown`, `DependencyDown`, `ApiErrorRateHigh` (over 5 %), `ApiLatencyHigh` (p95 over 2 s), `OutboxPublishFailures`, `DeadLettersIncreasing`, `AgentRunFailures`, `RedisErrors`, `DbPoolSaturation` |

---

## Known gaps and roadmap

Found while running and reviewing this code. Each item was reproduced or read in the source, and each has a concrete fix.

| # | Gap | Effect | Suggested fix |
| --- | --- | --- | --- |
| 1 | The API has no authentication; the console's operators are hard-coded | Anyone who can reach `:8000` can read any tenant by UUID and decide drafts under any name | OIDC in the console, signed service tokens to the API, tenant taken from the token |
| 2 | The reviewer role and requester ≠ decider are checked only in the console proxy | A direct API call let the requester approve their own draft (`200`) | Move both checks into `decide_draft` with an authenticated principal |
| 3 | Search `headline` uses `StartSel=,StopSel=` | Snippets come back as `",StopSel=svcbackup</b>"` | Quote the empty selectors or use real markers |
| 4 | Alert search text does not include `technique_ids` | The threat agent's search for `T1059.001` missed the EDR alert that stores that technique | Add technique IDs to `project_alert`, or query the GIN-indexed array |
| 5 | Console replay spawns `py -3`, the Windows launcher | Replay from Administration fails with `spawn py ENOENT` on Linux and macOS | Make the interpreter configurable, or add a replay endpoint |
| 6 | `/api/operations/*` is admin-only, but `/api/platform/api/v1/operations/*` is not | An analyst read dead-letter metadata through the generic proxy (`200`) | Apply the admin check to proxied operations paths |
| 7 | No HTTP surface to create or move cases, investigations, findings or alert status | Casework is written only with `soc_platform.casework` or SQL | Audited write endpoints with an editor role |
| 8 | `sqlalchemy>=2.0.36` is unpinned; the OTel SQLAlchemy instrumentation supports `< 2.1` | With SQLAlchemy 2.1 it logs an error and produces no database spans (metrics still work) | Pin `sqlalchemy<2.1` or upgrade the instrumentation |
| 9 | Grafana's Loki derived field expects `"trace_id":"…"`; logs emit `"trace_id": "…"` | Log-to-trace links do not appear | `separators=(",", ":")` in `JsonFormatter`, or relax the regex |
| 10 | Case detail keys every pending row `key="loading"` | Stale "Loading investigation" rows stay on screen | Key rows by investigation id |
| 11 | Host names are not canonicalised | `FS-02` and `FS-02.corp.example` would be two entities | Normalise FQDN and short name at projection |
| 12 | Group-membership events (4732) map `TargetUserName`, which is the group | The "user" entity becomes `Builtin\Administrators`; `MemberName` is kept only in `unmapped` | Map the member as the user and the group as a separate attribute |
| 13 | `soc_app` and `soc_relay` are created but unused | The relay and the inventory collector run as the table owner | Run the relay as `soc_relay`, or drop the unused roles |
| 14 | `agent_runs_total{status="failed"}` also counts refused requests | `network_denied` and agent-name requests count as failed runs although no run is stored | Separate a `rejected` status |
| 15 | No console tests, CI workflow or LICENSE | | Playwright smoke tests, a GitHub Actions workflow, a license |

**Next steps:** put a language model behind the same rails (it proposes `ClaimProposal`s; the validator and the approval gate stay as they are), real EDR and SIEM connectors, audited alert triage writes, and tenant-aware OIDC.

---

## Documentation index

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Processes, intake transaction, data model, OCSF mapping, tenancy and roles, search, agents, console, observability, design decisions |
| [docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md) | Every capability with its status and the code or test behind it |
| [docs/SETUP_GUIDE.md](docs/SETUP_GUIDE.md) | Docker and local installs, configuration, console, demo data, tests, troubleshooting, production checklist |
| [docs/API_REFERENCE.md](docs/API_REFERENCE.md) | All 26 operations with parameters, schemas, examples and error codes |
| [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md) | Captioned gallery of every screen |
| [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md) | A guided 15-minute demo with the bundled dataset |
| [demo/](demo) | Payload generator, seed script, investigation and decision driver |

<div align="center">

Built by **Nilesh P Raghavan** · [github.com/NileshModlier](https://github.com/NileshModlier)

<sub>The demo company, hosts, people and addresses are fictional; external IPs come from the RFC 5737 documentation ranges. MITRE ATT&CK® is a registered trademark of The MITRE Corporation. Sigma is an open detection format maintained by the SigmaHQ project.</sub>

</div>
