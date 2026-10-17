# Setup guide

- [1. Requirements](#1-requirements)
- [2. Option A: Docker Compose](#2-option-a-docker-compose)
- [3. Option B: local services without Docker](#3-option-b-local-services-without-docker)
- [4. Console](#4-console)
- [5. Demo data](#5-demo-data)
- [6. Ingesting your own payloads](#6-ingesting-your-own-payloads)
- [7. Tests](#7-tests)
- [8. Configuration reference](#8-configuration-reference)
- [9. Troubleshooting](#9-troubleshooting)
- [10. Production checklist](#10-production-checklist)

---

## 1. Requirements

| Tool | Version | Needed for |
| --- | --- | --- |
| Docker and Compose v2 | recent | Option A: PostgreSQL, Redis, API, relay, observability |
| PostgreSQL | 16 | Option B; the database must be **UTF-8** |
| Redis | 7 | Option B |
| Python | 3.12 or newer | CLI, API, relay, demo kit, tests |
| Node.js and npm | 20 or newer | console |
| Internet access | at console build or dev time | `next/font/google` downloads IBM Plex Sans and Mono |

Ports used: 5434 (PostgreSQL in Compose), 6379 (Redis), 8000 (API), 9101 (relay metrics), 3000 (console), 3001 (Grafana), 9090 (Prometheus), 9093 (Alertmanager), 3100 (Loki), 3200, 4317 and 4318 (Tempo).

---

## 2. Option A: Docker Compose

```bash
docker compose up -d --build
docker compose ps                      # migrate shows "exited (0)"; everything else is running
curl -s localhost:8000/ready           # {"status":"ok","postgres":"ok","redis":"ok"}
```

What starts:

| Service | Purpose |
| --- | --- |
| `postgres`, `redis` | data plane; PostgreSQL is published on host port **5434** |
| `migrate` | runs `alembic upgrade head` once, then exits |
| `api` | `uvicorn soc_platform.main:create_app --factory` on port 8000 |
| `outbox-relay` | publishes outbox rows to the Redis Stream `soc.outbox`; metrics on 9101 |
| `prometheus`, `alertmanager`, `grafana`, `loki`, `promtail`, `tempo` | metrics, alert rules, dashboards, logs, traces |

Install the Python package on the host as well, so you can run the CLI, the demo kit and the tests against the containers:

```bash
python -m venv .venv
source .venv/bin/activate              # PowerShell: .venv\Scripts\Activate.ps1
pip install -e '.[dev]'                # PowerShell: pip install -e ".[dev]"
cp .env.example .env                   # PowerShell: Copy-Item .env.example .env
```

`.env` points at `localhost:5434` and `localhost:6379`, which Compose publishes. You can also run the CLI inside the image:

```bash
docker compose run --rm -v "$PWD:/work" outbox-relay \
  soc-ingest ingest --tenant <uuid> --kind sigma_alert --file /work/alert.json
```

Stop with `docker compose down`. **Reset everything**, including the database, with `docker compose down -v`.

---

## 3. Option B: local services without Docker

### 3.1 PostgreSQL

The migrations create roles, enable `pgcrypto`, add triggers and RLS policies, and the API switches into `soc_reader` and `soc_agent` with `SET LOCAL ROLE`. The simplest local setup mirrors Compose, where the login role is a superuser:

```sql
-- as the postgres superuser
CREATE ROLE soc LOGIN SUPERUSER PASSWORD 'soc';
CREATE DATABASE soc OWNER soc ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;
```

> **Use a UTF-8 database.** A cluster initialised with the C locale defaults to `SQL_ASCII`. psycopg 3 then returns text as bytes, and every connection fails during SQLAlchemy's version check with `TypeError: cannot use a string pattern on a bytes-like object`. Creating the database with `ENCODING 'UTF8'` from `template0`, as above, avoids it.

If the login role cannot be a superuser, it needs `CREATEROLE`, ownership of the database, and membership in the scoped roles after the first migration: `GRANT soc_reader, soc_agent TO <login_role>;`. Without that membership `SET LOCAL ROLE` fails.

### 3.2 Redis

Any Redis 7 on `localhost:6379`. Persistence is optional for development.

### 3.3 Python services

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env                       # edit SOC_DATABASE_URL if your port is not 5434
alembic upgrade head

uvicorn soc_platform.main:create_app --factory --host 127.0.0.1 --port 8000   # terminal 1
soc-outbox-relay                                                             # terminal 2
```

`.env` is read from the current directory by the settings class and by Alembic, so run these from the repository root. Prometheus, Grafana and the rest are optional; without them, `/metrics` on the API and port 9101 on the relay still work. Set `SOC_OTLP_ENDPOINT=http://localhost:4317` only when a collector is listening.

---

## 4. Console

```bash
cd console
cp .env.example .env.local
# edit .env.local:
#   SOC_API_URL=http://127.0.0.1:8000
#   CONSOLE_SESSION_SECRET=<a long random string>
npm ci
npm run dev                       # http://localhost:3000
# or a production build
npm run build && npm start
```

| Variable | Default | Purpose |
| --- | --- | --- |
| `SOC_API_URL` | `http://127.0.0.1:8000` | where the BFF proxy sends API calls |
| `CONSOLE_SESSION_SECRET` | `dev-console-session` | HMAC key for the session cookie; always override |
| `SOC_DATABASE_URL`, `SOC_REDIS_URL` | the Compose values | passed to the replay subprocess only |

Sign in with an operator, its password, and a tenant UUID that exists in the database:

| Operator | Password | Can |
| --- | --- | --- |
| `analyst` | `analyst-local` | read everything, run investigations |
| `reviewer` | `reviewer-local` | the above, plus decide drafts in the review queue |
| `admin` | `admin-local` | the above, plus the administration page and replay |

The replay button on the administration page starts `py -3 -m soc_platform.cli replay …`, which exists only on Windows with the Python launcher. On Linux and macOS use the CLI: `soc-ingest replay --tenant <uuid> --source-record <uuid>`.

---

## 5. Demo data

Run once against a fresh database, from the repository root, with the API running:

```bash
python demo/make_payloads.py     # writes demo/payloads/ (34 files for Cobalt Ridge, 2 for Ashgrove Clinic)
python demo/seed_demo.py         # tenants, intake through the CLI, a duplicate, statuses, two replays, casework
python demo/run_agents.py        # 9 investigation requests and 4 decision requests through the API
```

Expected seed summary:

```text
Re-ingest cobalt-ridge/02-sigma-office-spawns-powershell.json: exit 0, duplicate=True, same source record=True
Totals: {'projected': 32, 'dead_lettered': 4, 'duplicate': 0, 'rejected': 0}
Replay cobalt-ridge/02-sigma-office-spawns-powershell.json: exit 0, receipt projected, alert status in_review, projection_generation 2
Replay of broken bytes: exit 2, receipt dead_lettered, dead_letter <uuid>
```

`seed_demo.py` is not idempotent: a second run adds a second set of cases. Start again with `docker compose down -v` (or drop and recreate the database), then `alembic upgrade head`. The full script is in [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md).

---

## 6. Ingesting your own payloads

1. Create a tenant (there is no tenant API):

   ```sql
   INSERT INTO tenants (id, slug, name, status, created_at, updated_at)
   VALUES (gen_random_uuid(), 'acme', 'Acme', 'active', now(), now()) RETURNING id;
   ```

2. Ingest files, one per call:

   ```bash
   soc-ingest ingest --tenant <uuid> --kind sigma_alert    --file alert.json
   soc-ingest ingest --tenant <uuid> --kind mock_edr_alert --file edr.json
   soc-ingest ingest --tenant <uuid> --kind windows_event  --file event.xml
   ```

3. Read the JSON result. `receipt_status` is `projected` or `dead_lettered`; `duplicate` is true when the same bytes were already stored for this tenant.

| Exit code | Meaning |
| :-: | --- |
| 0 | projected, or a duplicate of anything already stored |
| 2 | stored and dead-lettered (the bytes did not parse) |
| 3 | rejected and not stored: `tenant_not_found`, `tenant_disabled`, `payload_too_large`, `source_record_not_found` on replay |

Formats are described in [ARCHITECTURE.md §3](ARCHITECTURE.md#3-source-formats-and-ocsf-normalisation), and `demo/make_payloads.py` builds a working example of each.

To mark an alert as in review or closed today, update it directly; there is no status endpoint:

```sql
UPDATE alerts SET status = 'in_review' WHERE id = '<alert-uuid>';
UPDATE alert_search_documents SET status = 'in_review' WHERE id = '<alert-uuid>';
```

---

## 7. Tests

```bash
pytest -q                          # 57 tests
pytest -q -m "not integration"     # 30 tests; only the health test needs PostgreSQL and Redis
pytest -q tests/test_agent_workflow.py
```

Integration tests connect to `SOC_TEST_DATABASE_URL`, then `SOC_DATABASE_URL`, then `postgresql+psycopg://soc:soc@localhost:5434/soc`. They run `alembic upgrade head`, isolate each test in a rolled-back transaction or remove the tenants they create, and skip when PostgreSQL is unreachable. To keep demo data and tests apart:

```bash
psql postgresql://soc:soc@localhost:5434/soc -c \
  "CREATE DATABASE soc_test ENCODING 'UTF8' LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8' TEMPLATE template0;"
SOC_TEST_DATABASE_URL=postgresql+psycopg://soc:soc@localhost:5434/soc_test pytest -q
```

Most tests do not need Redis: the relay tests use `fakeredis`. The exception is `test_observability.py::test_health_carries_trace_headers_and_metrics_stay_out_of_openapi`, which is not marked `integration` but calls `/ready` and expects PostgreSQL on `localhost:5434` and Redis on `localhost:6379`. It fails, rather than skips, when either is down.

`tests/test_openapi.py` compares the running app's schema with `contracts/openapi.json`. After an intentional API change, regenerate the contract:

```bash
python -c "import json; from soc_platform.main import create_app; from soc_platform.config import Settings; \
print(json.dumps(create_app(Settings(database_url='postgresql+psycopg://x@localhost/x', redis_url='redis://localhost')).openapi(), indent=2, sort_keys=True))" \
  > contracts/openapi.json
```

This reproduces the checked-in file's layout (two-space indent, sorted keys). The test compares parsed JSON, so formatting alone never fails it.

---

## 8. Configuration reference

All Python settings are environment variables with the `SOC_` prefix (`soc_platform/config.py`), also read from `.env`.

| Variable | Default | Notes |
| --- | --- | --- |
| `SOC_DATABASE_URL` | required | `postgresql+psycopg://user:pass@host:port/db` |
| `SOC_REDIS_URL` | required | `redis://host:6379/0` |
| `SOC_API_CURSOR_SECRET` | `dev-only-change-me` | change outside development; rotating it invalidates every outstanding cursor |
| `SOC_MAX_PAYLOAD_BYTES` | `8388608` | larger payloads are rejected and not stored |
| `SOC_OUTBOX_STREAM` | `soc.outbox` | Redis Stream name |
| `SOC_OUTBOX_BATCH_SIZE` | `100` | rows claimed per relay transaction |
| `SOC_OUTBOX_MAX_ATTEMPTS` | `5` | publish attempts before `publish_exhausted` |
| `SOC_OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | sleep when a batch is empty |
| `SOC_SERVICE_NAME` | `soc-api` | the CLI defaults to `soc-ingest` and the relay to `soc-relay` unless this is set |
| `SOC_ENVIRONMENT` | `local` | trace resource attribute `deployment.environment` |
| `SOC_OTLP_ENDPOINT` | empty | e.g. `http://tempo:4317`; empty disables export |
| `SOC_METRICS_ENABLED` | `true` | `false` makes `/metrics` return 404 and stops the inventory collector |
| `SOC_METRICS_PORT` | `9101` | relay metrics server |
| `SOC_LOG_FORMAT` | `json` | `text` for human-readable logs |

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `TypeError: cannot use a string pattern on a bytes-like object` on the first connection | `SQL_ASCII` database | Recreate it with `ENCODING 'UTF8'` from `template0` (§3.1) |
| `RuntimeError: SOC_DATABASE_URL is required to run Alembic` | no `.env` in the current directory | `cp .env.example .env`, run from the repository root |
| `permission denied to set role "soc_reader"` | login role is neither superuser nor a member | `GRANT soc_reader, soc_agent TO <login_role>;` |
| API returns `404 tenant_not_found` | the tenant UUID does not exist | insert the tenant (§6) |
| `422 invalid_filter` | a query parameter the operation does not accept, such as `sort` on `/alerts` | use the parameters listed in [API_REFERENCE.md](API_REFERENCE.md) |
| `400 invalid_cursor` | the cursor came from a different filter set, tenant or `limit` | send the same filters and limit as the page that produced it |
| Console shows "The platform API is not reachable." (`502 api_unreachable`) | API down or `SOC_API_URL` wrong | start the API; check `.env.local` |
| Console redirects to `/login` repeatedly | `CONSOLE_SESSION_SECRET` changed or the cookie expired | sign in again |
| Replay on the administration page fails with `spawn py ENOENT` | not Windows | use `soc-ingest replay` |
| `next dev` or `next build` cannot download IBM Plex | no access to Google Fonts | allow `fonts.googleapis.com` and `fonts.gstatic.com`, or switch `app/layout.tsx` to `next/font/local` with bundled files |
| Log line `SQLAlchemyInstrumentor only instruments "sqlalchemy >= 1.0.0, < 2.1.0"` | pip installed SQLAlchemy 2.1 | `pip install 'sqlalchemy<2.1'` to get database spans; everything else works without it |
| `/ready` returns `503` | PostgreSQL or Redis unreachable from the API | check both URLs; the body says which one failed |
| Outbox rows stay `pending` | relay not running or Redis down | start `soc-outbox-relay`; check `outbox_publish_failures_total` |
| Port 5434 already in use | another PostgreSQL | change the host port in `docker-compose.yml` and `.env` |

---

## 10. Production checklist

This codebase is a well-built foundation, not a hardened deployment. Before exposing it:

- [ ] Put real authentication in front of the API (OIDC at the console, signed service tokens to the API) and derive the tenant from the token, not a query parameter.
- [ ] Enforce the reviewer role and requester ≠ decider inside `decide_draft`, not only in the console.
- [ ] Replace the hard-coded console operators; set a strong `CONSOLE_SESSION_SECRET` and serve the console over HTTPS so the cookie can be marked `Secure`.
- [ ] Set `SOC_API_CURSOR_SECRET` from a secret store.
- [ ] Use a non-superuser login role that owns the schema and is a member of `soc_reader` and `soc_agent`; run the relay as `soc_relay` or remove the unused roles.
- [ ] Keep the API on a private network reachable only from the console.
- [ ] Pin `sqlalchemy<2.1` (or upgrade the OpenTelemetry instrumentation) and pin the rest of the dependency set.
- [ ] Gate `/api/platform/api/v1/operations/*` to administrators in the console middleware.
- [ ] Add a retention policy for `source_records`, `outbox_events` and `agent_memories`.
- [ ] Configure Alertmanager receivers; the bundled configuration has none.
- [ ] Change the Grafana admin password and the PostgreSQL credentials in `docker-compose.yml`.
- [ ] Add CI that runs the test suite against PostgreSQL 16, plus console smoke tests.
