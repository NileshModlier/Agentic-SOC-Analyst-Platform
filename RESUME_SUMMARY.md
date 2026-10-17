# Resume-ready project summary

Material for a resume, LinkedIn, a portfolio page and interviews. Every number here is taken from the repository or from a run of it; the [last section](#keep-it-accurate) lists what not to claim.

---

## One line

**Agentic SOC Analyst Platform:** a multi-tenant security operations platform that keeps raw detections as immutable evidence, normalises them to OCSF, searches them in PostgreSQL, and runs a LangGraph investigation workflow whose cited claims are validated against the database before a person approves them.

## Project blurb (portfolio or LinkedIn, about 90 words)

> I built a security operations platform around one rule: nothing an AI-style agent says counts until it is tied to stored evidence and a person signs off. Sigma, EDR and Windows event payloads are stored byte for byte, normalised to OCSF and projected into tenant-isolated alerts, evidence and full-text search in a single transaction. A LangGraph supervisor and four specialist agents investigate using nine read-only tools, write templated claims that cite exact rows, and re-check every citation before a reviewer approves. Python, FastAPI, PostgreSQL row-level security, Redis Streams, Next.js and OpenTelemetry, with 57 automated tests.

## Thirty-second pitch

"SOC teams want AI help, but they can't act on conclusions they can't trace. I built the rails first. Every alert is rebuilt from hashed raw bytes, tenants are isolated inside PostgreSQL with row-level security, and the investigation agents can only read nine local tools and fill six claim templates. Before a draft is saved, every claim is reloaded and compared with the row it cites, and only a person can approve it. Approval never rewrites the evidence. It's fully observable and covered by 57 tests."

---

## Resume bullets

### General version (four bullets)

- Built a **multi-tenant security operations platform** (Python, FastAPI, PostgreSQL 16, Redis) that stores raw Sigma, EDR and Windows event payloads immutably (SHA-256, database triggers), normalises them to an **OCSF 1.5-aligned** schema across 9 event classes, and projects alerts, evidence and search rows in one transaction with a **transactional outbox** to Redis Streams, dead letters and byte-exact replay.
- Enforced **tenant isolation inside PostgreSQL** with row-level security on all 24 tables, composite tenant foreign keys and per-request `SET LOCAL ROLE` into least-privilege roles, with column-level grants that keep raw bytes out of every API path.
- Designed a **LangGraph investigation workflow** (supervisor plus triage, entity, threat and reporting agents) limited to 9 read-only tools; its templated claims are **re-validated against the cited database rows** before a **human approval gate** with separation of duties.
- Delivered **PostgreSQL full-text search** with identifier folding, facets and HMAC-signed keyset cursors, a 26-operation OpenAPI contract guarded by tests, a 13-page Next.js console, and full observability (31 Prometheus metric families, OpenTelemetry traces, JSON logs, Grafana, 10 alert rules), with **57 automated tests**.

### Agentic AI Engineer · Applied AI Engineer · Generative AI Engineer

- Architected a **LangGraph multi-agent investigation workflow** (supervisor routing four specialists) with typed state, append-only run memory, per-node savepoints and a hard recursion limit, so a failing tool or node ends the run as `failed` instead of producing an unverified answer.
- Built **grounding and guardrails before the model**: a closed registry of 9 tool functions, URL and network-argument refusal, six claim templates filled only from stored fields, and a validator that reloads every cited record and rejects the draft on any mismatch (`validation_failed`) or empty evidence (`insufficient_evidence`).
- Designed a **human-in-the-loop approval gate** where agents cannot approve, agent names cannot act as people, a draft is decided once, and approval records a decision without changing any canonical record (enforced by a `source_of_truth = false` check constraint and a write-limited database role).
- Instrumented agent runs end to end with **OpenTelemetry spans per node** and Prometheus counters for runs, drafts, citation failures, insufficient evidence, approvals and review latency.

### AI Infrastructure Engineer · Platform or Backend Software Engineer

- Implemented an **event-driven intake pipeline** with a transactional outbox: one database transaction writes immutable bytes, projections, search rows and the outbox row; a relay publishes to **Redis Streams** with `FOR UPDATE SKIP LOCKED`, at-least-once delivery, exponential back-off and dead letters after a fixed attempt budget.
- Designed a **26-operation read API** in FastAPI and Pydantic v2 with a strict query-parameter allow-list, a single error envelope, HMAC-signed keyset cursors bound to tenant, filters and page size, and a checked-in OpenAPI contract that fails the test suite on drift.
- Modelled **24 PostgreSQL tables** with composite tenant keys, row-level security, generated `tsvector` columns with GIN indexes, immutability triggers and hash-verifying check constraints, across 6 Alembic migrations.
- Shipped **production-style operations**: Docker image running as non-root, an 11-service Compose stack, liveness and readiness probes, 31 metric families, 10 Prometheus alert rules and a provisioned 32-panel Grafana dashboard.

### Security Engineer · SOC Automation · Detection Engineering

- Normalised **Sigma rule matches, EDR alerts and Windows Security, System and Sysmon events** (XML in UTF-8 and UTF-16, Event JSON, Winlogbeat) into OCSF, mapping 15 event IDs and ATT&CK techniques and tactics from Sigma tags.
- Built **chain-of-custody storage**: per-tenant SHA-256 deduplication, immutable raw records and evidence, database-verified hashes, dead-lettering of malformed telemetry with reason codes, and replay that rebuilds every derived row from the original bytes while preserving analyst workflow state.
- Delivered an **analyst console** (Next.js 15, React 19) with alert triage, facets, an entity catalogue, case and investigation timelines, an agent workspace and a review queue with role gates and requester ≠ approver separation.

### AI Evaluation · QA for AI products

- Built a **deterministic evaluation harness for agent output**: each claim is a structured proposal (template, citation kind, record id, arguments) validated against the database, with seven explicit failure reasons and three draft outcomes that are counted as metrics.
- Wrote **57 tests** covering forged claims, missing records, refused network access, agent self-approval, tool failures that must never approve, tenant isolation and API contract drift; verified the platform end to end with a 36-payload adversarial demo dataset including malformed inputs.

---

## Numbers you can quote

| Metric | Value | Source |
| --- | --- | --- |
| Python application code | about 10,500 lines in 87 modules | `soc_platform/` |
| Console code | about 3,400 lines in 57 files | `console/src/` |
| Tests | 57 (30 unit, 27 integration), all passing in about 6 seconds | `pytest -q` |
| API operations | 26 (24 GET, 2 POST) across 25 paths and 65 schemas | `contracts/openapi.json` |
| Database | 24 tables, all with row-level security; 6 migrations; 2 scoped runtime roles | `alembic/versions/` |
| Input formats | 3 source kinds; Windows in 3 shapes and 2 encodings; 15 mapped event IDs | `soc_platform/ingestion/` |
| OCSF classes | 9 | demo dataset produces all nine |
| Agents and tools | supervisor plus 4 specialists; 9 tools; 6 claim templates | `soc_platform/agents/` |
| Observability | 31 metric families, 10 alert rules, 32 Grafana panels | `soc_platform/observability/`, `deploy/` |
| Console | 13 pages, 3 roles | `console/src/app/` |
| Demo | 36 payloads, 4 malformed; one investigation in under 200 ms | `demo/` |

## Keywords for applicant tracking systems

Python · FastAPI · Pydantic · SQLAlchemy · Alembic · PostgreSQL · row-level security · full-text search · Redis Streams · transactional outbox · event-driven architecture · LangGraph · multi-agent systems · agentic AI · tool calling · guardrails · grounding · citation validation · human-in-the-loop · OCSF · Sigma · EDR · Windows Event Log · Sysmon · MITRE ATT&CK · SOC automation · multi-tenancy · OpenAPI · REST · Next.js · React · TypeScript · TanStack Query · Tailwind CSS · OpenTelemetry · Prometheus · Grafana · Loki · Tempo · Docker · Docker Compose · pytest

---

## Interview talking points

**"Walk me through the architecture."** Raw payload in through a CLI; one transaction stores the bytes under their hash, parses them, writes the OCSF event, the alert, evidence, search rows and an outbox row. A relay pushes the outbox to Redis Streams. FastAPI serves reads and search under row-level security and runs the LangGraph workflow in-process. A Next.js backend-for-frontend holds the session and is the only thing that talks to the API.

**"Why the transactional outbox?"** Writing to the database and publishing to a stream are two systems; without an outbox, a crash between them loses or duplicates events. Here the outbox row commits with the data, and the relay delivers at least once. Consumers dedupe on `event_id`.

**"How do you stop the agent from hallucinating?"** It cannot write free text. Specialists propose claims as structured tuples: template, citation kind, record id, arguments. The reporting step reloads each cited row and compares every argument; one mismatch marks the whole draft `validation_failed`. No evidence means `insufficient_evidence`. Then a person decides, and approval changes nothing but the draft.

**"Where would an LLM go?"** Into the specialists, as a proposer of `ClaimProposal`s, and maybe into planning. The tool registry, the validator, the write-limited `soc_agent` role and the approval gate stay exactly where they are, so a model can make the drafts better without being able to make them less trustworthy.

**"How does multi-tenancy work?"** Three layers: composite `(tenant_id, id)` foreign keys so rows cannot reference across tenants, RLS policies keyed on a transaction-local setting, and `SET LOCAL ROLE` into a non-owner role with a runtime check before each query, because the table owner would bypass RLS.

**"Why PostgreSQL full-text search instead of Elasticsearch?"** One system of record, the same RLS for search as for everything else, and search rows written in the intake transaction. The cost is relevance tuning. The interesting part was identifier folding, so `203.0.113.45` is one token rather than four.

**"What would you fix first?"** Authentication on the API, so the tenant comes from a token. Then move the reviewer-role and self-approval checks from the console into the API, fix the search snippet options, and index technique ids so the threat agent finds related alerts. The README lists 15 gaps I found by running it, each with a fix.

**"What was hardest?"** Replay semantics: rebuilding projections from stored bytes while keeping analyst-owned state such as alert status, refreshing search and entity statistics in place, and making a failed replay leave the previous projection intact.

---

## Keep it accurate

Say these plainly if asked, and avoid wording that implies otherwise:

- **No language model is called.** The agents are deterministic LangGraph nodes. Describe them as an agentic workflow with LLM-ready guardrails, not as LLM agents.
- **No production deployment or users.** It runs locally with Docker Compose and synthetic data. Avoid figures such as "alerts per day" or "MTTR reduced".
- **The EDR source is a mock format**, not a vendor integration, and intake is a CLI, not a live connector.
- **The API has no authentication**, and the reviewer and self-approval checks live in the console.
- **Casework is created through a Python module or SQL**, not through the API.
