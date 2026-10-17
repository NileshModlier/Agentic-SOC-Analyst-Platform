# Demo kit

Three scripts that load a fictional five-day intrusion into a fresh database and drive the investigation workflow and human decisions. The walkthrough that uses them is [docs/DEMO_WALKTHROUGH.md](../docs/DEMO_WALKTHROUGH.md).

| File | What it does |
| --- | --- |
| `make_payloads.py` | Writes `payloads/cobalt-ridge/` (34 files) and `payloads/ashgrove-clinic/` (2 files) plus `payloads/manifest.json`. Deterministic: the same bytes every run. |
| `seed_demo.py` | Creates the two tenants, ingests every file with `soc-ingest`, re-ingests one to show deduplication, sets three alerts to `in_review` and one to `closed`, replays one good and one broken record, and creates cases, investigations, findings and links with `soc_platform.casework`. Writes `state.json` with the ids. |
| `run_agents.py` | Calls the API: nine investigation requests (alerts, questions, an unknown alert, a URL, an agent name) and four decision requests (approve, decide twice, reject with `[changes-requested]`, agent name as actor). |

## Run

From the repository root, with migrations applied and the API on `http://127.0.0.1:8000` (override with `SOC_API_URL`):

```bash
python demo/make_payloads.py     # optional: payloads/ is already included
python demo/seed_demo.py
python demo/run_agents.py
```

Console sign-in: tenant `6c1f2b9e-4d7a-4f3e-9b21-0a5c8e7d3f14`, operators `analyst`, `reviewer`, `admin` with passwords `<operator>-local`.

## Data

- Company: **Cobalt Ridge Logistics**, Windows domain `CRL`; hosts `FIN-LT-07`, `FS-02`, `DC-01`, `HR-LT-03`; people `m.okafor`, `svc_backup`, `j.lindqvist`, `helpdesk_tmp`.
- External addresses come from RFC 5737 (`203.0.113.45`, `198.51.100.23`) and names use the reserved `.example` domain.
- Formats: Sigma JSON with and without a matched event, mock EDR JSON, Windows Event XML (including one UTF-16 file), Event JSON and Winlogbeat JSON.
- Files `90` to `93` are broken on purpose: truncated JSON, a missing `alert_id`, malformed XML and a missing `TimeCreated`.
- Ashgrove Clinic's `01-shared-bytes.xml` is byte-for-byte identical to Cobalt Ridge's file `20`.

## Notes

- `seed_demo.py` is not idempotent. A second run duplicates the cases and replays again. Reset with `docker compose down -v` before reloading.
- The seed writes tenants and alert statuses with SQL because the platform has no API for either.
- Casework dates are moved onto the story timeline (5 to 9 October 2026) so the console reads naturally; intake and run timestamps are real.
- All names, hosts and events are fictional.
