# Feature matrix

Every line points at the code that implements it and, where one exists, the test that proves it. Status reflects a local run with PostgreSQL 16, Redis 7, Python 3.12 and the bundled demo data.

| Mark | Meaning |
| :-: | --- |
| ✅ | Implemented and exercised by a test or the demo |
| 🟡 | Implemented with a limitation noted in the same row |
| ⚠️ | Partial, demo grade, or enforced in only one layer |
| ❌ | Not implemented |

## Intake and custody

| Capability | Status | Evidence |
| --- | :-: | --- |
| Sigma rule-match JSON, with the matched Windows event as the canonical activity | ✅ | `ingestion/sigma.py`; `test_parsers.py::test_sigma_projects_rule_and_underlying_process` |
| Sigma match with no event becomes a Detection Finding | ✅ | `test_parsers.py::test_sigma_without_a_match_is_a_detection_finding` |
| Mock EDR alert JSON (process, network or finding) | ✅ | `ingestion/mock_edr.py`; `test_parsers.py::test_mock_edr_projects_process_alert` |
| Windows Event XML, UTF-8 and UTF-16 | ✅ | `ingestion/windows_event.py`; `test_parsers.py::test_windows_xml_process_create_accepts_utf16` |
| Windows Event JSON and Winlogbeat JSON | ✅ | `_from_json`, `_from_winlogbeat`; demo payloads 04, 08, 17, 18, 21 |
| Seven-digit fractional seconds and offsets without a colon | ✅ | `ingestion/codec.py::parse_timestamp`; `test_windows_security_json_logon_keeps_seven_digit_fraction` |
| 15 Windows event IDs mapped to 8 OCSF classes; others become Base Event | ✅ | `ingestion/taxonomy.py` |
| Immutable raw store (`UPDATE`/`DELETE` rejected by trigger) | ✅ | migration `9f0fe331d361`; `test_phase1.py::test_source_and_evidence_rows_are_immutable` |
| Hash and size checks in the database | ✅ | `ck_source_records_sha256`, `ck_source_records_byte_size`; `test_source_hash_must_match_payload` |
| Per-tenant SHA-256 deduplication | ✅ | `uq_source_records_hash`; `test_duplicate_bytes_do_not_create_a_second_outbox_row`, `test_same_bytes_are_isolated_per_tenant` |
| Size limit (`SOC_MAX_PAYLOAD_BYTES`, default 8 MiB), nothing stored | ✅ | `test_oversized_payload_is_rejected_without_storage` |
| Disabled or unknown tenant rejected | ✅ | `test_disabled_tenant_is_rejected` |
| Parse failures stored and dead-lettered with a reason code | ✅ | `test_invalid_payload_is_stored_and_dead_lettered`; demo payloads 90 to 93 |
| One transaction for bytes, projections, links, search and outbox | ✅ | `pipeline.py`; `test_sigma_ingest_is_transactional_and_replayable`, `test_outbox_is_invisible_until_commit` |
| Replay from stored bytes, alert status preserved | ✅ | `pipeline.replay`; `test_replay_preserves_alert_workflow_status`; demo replay raised `projection_generation` to 2 with `in_review` kept |
| Replay failure keeps the existing projection and adds a replay dead letter | ✅ | `test_replay_failure_keeps_the_existing_projection` |
| Evidence custody record with links to alerts, events and casework | ✅ | `models/evidence.py`; `test_api.py::test_casework_and_evidence_reads` |
| Ingest over HTTP | ❌ | Intake is the `soc-ingest` CLI only |
| Real connectors (EDR vendor API, SIEM pull, syslog) | ❌ | Payloads are supplied as files |

## Normalisation

| Capability | Status | Evidence |
| --- | :-: | --- |
| OCSF 1.5 subset document with `type_uid`, severity and outcome ids | ✅ | `domain/canonical.py` |
| 9 OCSF classes (Authentication, Process, File System, Network, User Management, Group Management, Event Log, Application Lifecycle, Detection Finding) | ✅ | demo tenant has all nine |
| Observables (user, hostname, ip, domain, port, process name, hash, file path) | ✅ | `canonical._observables` |
| ATT&CK techniques and tactics from Sigma tags and EDR fields | ✅ | `codec.techniques_from_tags` |
| Host-name canonicalisation (FQDN vs short name) | ❌ | `search/extract.normalize_value` only case-folds |
| Group membership member mapping (4732) | 🟡 | The group lands in `user`; `MemberName` stays in `unmapped` |

## Eventing

| Capability | Status | Evidence |
| --- | :-: | --- |
| Transactional outbox, five event types | ✅ | `domain/events.py`, `pipeline._add_outbox` |
| Relay to Redis Streams with `FOR UPDATE SKIP LOCKED` | ✅ | `outbox/publisher.py`; `test_publisher_writes_redis_then_marks_published` |
| Exponential back-off (max 60 s) and `publish_exhausted` dead letter | ✅ | `test_publisher_backs_off_before_dead_letter`, `test_publisher_dead_letters_after_the_attempt_budget` |
| Consumer-side dedupe key (`event_id`) | ✅ | stream field `event_id`; demo stream held 38 entries for 36 intakes and 2 replays |
| Stream consumers | ❌ | Nothing in the repository reads `soc.outbox` |

## Tenancy and access

| Capability | Status | Evidence |
| --- | :-: | --- |
| Composite `(tenant_id, id)` foreign keys on every child | ✅ | `models/*`; `test_cross_tenant_alert_reference_is_rejected`, `test_casework_links_stay_inside_the_tenant` |
| RLS on all 24 tables | ✅ | migrations; `test_row_level_security_hides_other_tenants` |
| `SET LOCAL ROLE soc_reader` / `soc_agent` with a runtime guard | ✅ | `api/reader.py`; `test_reader_role_is_select_only_and_tenant_scoped` |
| Column-level grants keep raw bytes and outbox payloads out of the API role | ✅ | migrations `c4a8e1b92d07`, `b7e2c4a91d08` |
| Cross-tenant read returns 404 | ✅ | `test_events_filters_pagination_and_tenant_isolation`; demo: tenant B asking for a tenant A alert got `404 not_found` |
| API caller authentication | ❌ | The API trusts `?tenant=`; README gap 1 |
| Console sign-in | ⚠️ | Three hard-coded operators, HMAC-signed cookie, 12-hour expiry |
| Role gates (analyst, reviewer, admin) | ⚠️ | Console middleware and proxy only; `/api/platform/api/v1/operations/*` is not admin-gated (gap 6) |
| Unused roles `soc_app`, `soc_relay` | 🟡 | Created and granted; no process assumes them |

## Read API

| Capability | Status | Evidence |
| --- | :-: | --- |
| 26 operations: 24 GET and 2 POST | ✅ | `test_surface.py::test_registers_only_read_routes` |
| Checked-in OpenAPI contract equals the app | ✅ | `contracts/openapi.json`; `test_openapi.py`; live `/openapi.json` matched in the run |
| Query-parameter allow-list (`422 invalid_filter`) | ✅ | `routes.allow_query`; `test_request_contract` |
| Stable error envelope for 400, 404, 405, 409, 422, 500 | ✅ | `api/errors.py`; recorded in [API_REFERENCE.md](API_REFERENCE.md#errors) |
| HMAC-signed keyset cursors bound to tenant, filters and limit | ✅ | `api/pagination.py`; `test_pagination.py` |
| Default page 50, maximum 100 | ✅ | `PageQuery` |
| Write endpoints for casework or alert status | ❌ | `soc_platform/casework.py` has Python functions with no HTTP surface |

## Search

| Capability | Status | Evidence |
| --- | :-: | --- |
| Full-text search over events, alerts and entities | ✅ | `api/search_queries.py`; `test_search.py::test_search_filters_facets_sort_and_cursor` |
| Identifier folding for IPs, paths and process names | ✅ | `search/text.py`; `test_search_text.py` |
| Facets that omit their own filter; top 20 hosts and users | ✅ | `search_facets` |
| Sorts: event time, created time, severity | ✅ | `_event_sort`, `_alert_sort`, `_entity_sort` |
| Replay updates search rows in place | ✅ | `test_replay_updates_search_in_place` |
| Highlighted snippets (`headline`) | 🟡 | Returns `",StopSel=<token></b>"` because of unquoted empty selectors (gap 3) |
| Technique IDs searchable on alerts | 🟡 | Only when the technique appears in the title or description (gap 4) |

## Investigation workflow

| Capability | Status | Evidence |
| --- | :-: | --- |
| LangGraph supervisor plus triage, entity, threat and reporting | ✅ | `agents/graph.py`, `agents/nodes.py`; `test_agent_workflow.py` |
| Closed registry of 9 local read tools | ✅ | `agents/tools.py`; `test_tool_registry_is_a_closed_local_set` |
| No network imports in the agent package | ✅ | `test_agent_package_does_not_import_network_clients` |
| URL questions and URL-shaped tool arguments refused (`network_denied`) | ✅ | `agents/network.py`; `test_urls_are_refused`; demo returned `422 network_denied` |
| 6 claim templates rendered from stored fields | ✅ | `agents/citations.py`; `test_claim_text_is_rendered_from_the_template` |
| Every citation reloaded and compared before storing | ✅ | `validate_proposal`; `test_unknown_claim_template_is_rejected_without_a_database_lookup` |
| Draft outcomes `pending_approval`, `insufficient_evidence`, `validation_failed` | ✅ | demo produced the first two; `test_agent_workflow.py` rejects a forged title and a missing record, and refuses a draft row with `source_of_truth = true` |
| Append-only run memory | ✅ | `agents/memory.py`; shown on the workspace page |
| Tool failure never approves | ✅ | `test_tool_failure_does_not_approve_a_draft` |
| Agents cannot store an approved draft | ✅ | `drafts.store_draft`; `test_agents_cannot_store_an_approved_draft` |
| Language model reasoning | ❌ | Deterministic nodes; no model is called |

## Human review

| Capability | Status | Evidence |
| --- | :-: | --- |
| Approve or reject a pending draft, once | ✅ | `drafts.decide_draft`; demo: second decision returned `409 conflict` |
| Agent names refused as requester or actor | ✅ | `agents/actors.py`; `test_people_are_required`; demo returned `422` |
| Approval does not create a finding or change an alert | ✅ | `test_workflow_drafts_cited_claims_and_requires_a_person` |
| Request changes (stored as a rejection with `[changes-requested]`) | ✅ | console `lib/api-proxy.ts`; demo LSASS draft |
| Reviewer role required to decide | ⚠️ | Console proxy only |
| Requester cannot decide their own draft | ⚠️ | Console proxy only; a direct API call returned `200` (gap 2) |

## Console

| Capability | Status | Evidence |
| --- | :-: | --- |
| 13 pages: login, dashboard, alerts, alert detail, cases, case detail, investigations, investigation timeline, entities, entity detail, agent workspace, review queue, administration | ✅ | `console/src/app`; screenshots 01 to 14 |
| BFF proxy that injects the tenant and the acting person | ✅ | `app/api/platform/[...path]/route.ts` |
| Role-filtered navigation | ✅ | `components/shell.tsx` |
| Sentinel page guide, nine pages of content, dark and light | ✅ | `components/sentinel/` |
| Production build | ✅ | `next build` succeeded (Next.js 15.5.27) |
| Replay from the console | ⚠️ | Spawns `py -3`; fails on Linux and macOS (gap 5) |
| Case detail investigations list | 🟡 | Stale "Loading investigation" rows (gap 10) |
| Console tests | ❌ | None |

## Observability

| Capability | Status | Evidence |
| --- | :-: | --- |
| JSON logs with correlation, trace and span ids | ✅ | `observability/logging.py`; `test_json_logs_carry_service_and_correlation` |
| Correlation id accepted only when well formed | ✅ | `test_correlation_id_rejects_injected_values` |
| OpenTelemetry spans for HTTP, search, intake, outbox, Redis and agent nodes | ✅ | `observability/tracing.py`, `hooks.py` |
| SQLAlchemy spans | 🟡 | Disabled when SQLAlchemy 2.1 is installed (gap 8) |
| 31 Prometheus metric families | ✅ | `metrics.py`, `inventory.py`; scraped in the run |
| `/health` and `/ready` (`503` on dependency failure) | ✅ | `observability/health.py`; `test_health_carries_trace_headers_and_metrics_stay_out_of_openapi` |
| 10 Prometheus alert rules | ✅ | `promtool check rules`: 10 found; `DeadLettersIncreasing` and `AgentRunFailures` went pending in the run |
| Grafana dashboard with 32 panels | ✅ | `grafana/dashboards/soc.json` |
| Loki to Tempo log links | 🟡 | Derived-field regex does not match the log format (gap 9) |

## Delivery

| Capability | Status | Evidence |
| --- | :-: | --- |
| Dockerfile, non-root | ✅ | uid 10001 |
| Docker Compose, 11 services | ✅ | `docker-compose.yml` |
| Alembic migrations | ✅ | 6 revisions, each with a downgrade step (downgrades are not tested) |
| 57 automated backend tests | ✅ | `pytest -q`: 57 passed; one test outside the `integration` marker needs live PostgreSQL and Redis |
| CI workflow | ❌ | No `.github/workflows` |
| License | ❌ | No `LICENSE` file |

The full list of gaps, with effects and fixes, is in the README under [Known gaps and roadmap](../README.md#known-gaps-and-roadmap).
