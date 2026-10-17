# Screenshots

Every image was captured from this repository running locally: the FastAPI service, the outbox relay, the Next.js console (`next build && next start`), PostgreSQL 16, Redis 7, and Prometheus 2.55 with the repository's own rule file. The data is the demo dataset from [`demo/`](../demo), loaded with the steps in [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md). Images are 1600 pixels wide.

The demo company, Cobalt Ridge Logistics, is fictional. Its Windows domain is `CRL`, internal hosts are `FIN-LT-07`, `FS-02`, `DC-01` and `HR-LT-03`, and external addresses come from the RFC 5737 documentation ranges.

- [Walkthrough animation](#walkthrough-animation)
- [Analyst](#analyst)
- [Agent workspace](#agent-workspace)
- [Reviewer](#reviewer)
- [Administrator](#administrator)
- [Page guide](#page-guide)
- [API and metrics](#api-and-metrics)

---

## Walkthrough animation

![Walkthrough](screenshots/demo-walkthrough.gif)

Nine frames, about 2.6 seconds each: sign-in, dashboard, IP search, alert detail, an investigation run, the review queue, the approval, the separation-of-duties refusal, and the administration page.

---

## Analyst

### Sign-in

![Login](screenshots/01-login.png)

Three local operators and a tenant UUID. The console signs a session cookie with the operator's role, name and tenant; the browser never chooses a tenant again after this page.

### Dashboard

![Dashboard](screenshots/02-dashboard.png)

Seven open (`new`) alerts and seven high or critical, one active case, three drafts awaiting a person, and three open or active investigations. Alert trend covers 5 to 9 October. Severity distribution and entity activity come from event facets, which count the whole event corpus; the cards count the latest page of up to 100 rows, as the page header says.

### Alert explorer

![Alert explorer](screenshots/03-alert-explorer.png)

All eleven Cobalt Ridge alerts, newest first, with severity and workflow status. The facet rail counts the 30 events: nine OCSF classes, three sources, four hosts. Three alerts are `in_review` and one is `closed`; the seed set those statuses, and a replay kept them.

### IP search

![IP search](screenshots/03b-alert-search-ip.png)

Searching `203.0.113.45` returns the beaconing alert. The address is folded to a single token at index and query time, so it matches exactly instead of matching four separate numbers.

### Alert detail

![Alert detail](screenshots/04-alert-detail.png)

The Sigma rule "Office Application Spawning PowerShell" beside its linked canonical event: `WINWORD.EXE` launched `powershell.exe -nop -w hidden -enc …` as `CRL\m.okafor` on `FIN-LT-07`. Techniques `T1059.001` and `T1566.001` come from the rule's tags. **Run investigation** opens the agent workspace with this alert filled in.

### Entity explorer

![Entities](screenshots/05-entities.png)

Hosts, each with its highest linked severity, event count, and first and last seen times. Users, processes, files and IPs are tabs on the same catalogue.

### Entity detail

![Entity detail](screenshots/06-entity-detail.png)

`CRL\svc_backup`: thirteen linked events from the four failed logons on 6 October through the log clearing on 9 October, and the two alerts whose events name the account.

### Cases

![Cases](screenshots/07-cases.png)

The open critical case INC-0412 and a closed low-severity case. Cases are read-only in the console; the seed created them with `soc_platform.casework`.

### Case detail

![Case detail](screenshots/08-case-detail.png)

Three investigations and two findings. The two "Loading investigation" lines are a real defect: every pending row shares `key="loading"`, so placeholders stay after the data arrives (README gap 10).

### Investigations

![Investigations](screenshots/09-investigations.png)

Priority, status and assignee for each unit of analysis.

### Investigation timeline

![Investigation timeline](screenshots/10-investigation-timeline.png)

"svc_backup used for lateral movement to FS-02": the investigation opening, its four linked alerts, and the agent runs started for those alerts, merged in time order.

---

## Agent workspace

### A completed run

![Agent workspace](screenshots/11-agent-workspace.png)

The analyst ran an investigation on "User Added to Local Administrators". The run completed and the draft is `pending_approval`. Every claim names its template and links to the record it cites: the alert and its two techniques, the 4732 event, the custody record with its SHA-256, and two entities. The memory list shows the order of work: supervisor plan, triage observations and claims, entity lookups, threat searches, and the reporting step. There is no chat box.

The entity claim reads "Stored user Builtin\Administrators", because event 4732 names the group in `TargetUserName` (README gap 12).

### Insufficient evidence

![Insufficient evidence](screenshots/11b-agent-workspace-insufficient.png)

The question `mimikatz` matches no stored record, so the run completes with an `insufficient_evidence` draft and no claims. Nothing is invented.

### Failed run

![Failed run](screenshots/11c-agent-workspace-failed.png)

A random alert id fails as `alert_not_found` after one triage observation. No draft is stored.

---

## Reviewer

### Review queue

![Review queue](screenshots/12-review-queue.png)

Signed in as `reviewer`. Pending drafts on the left; the selected draft shows the notice that it is not a source of truth, every claim with its citation, and a note. **Request changes** records a rejection with the note marked `[changes-requested]`.

### After approval

![Approved](screenshots/12b-review-approved.png)

The draft is `approved` and the decision line shows the reviewer, the time and the note. Recent decisions list approvals, a rejection shown as "Changes requested", and the actor for each.

### Separation of duties

![Self-approval blocked](screenshots/12c-review-self-approval-blocked.png)

The reviewer started a run themselves, then tried to approve its draft. The console refuses: "The person who requested the investigation cannot decide the draft." The API does not repeat this check (README gap 2).

---

## Administrator

### Administration

![Administration](screenshots/13-administration.png)

Connector health per source (projected and dead-lettered receipts, last intake time), the replay form, six dead letters with stage, reason code and attempts, the human decision record, and outbox publications. The extra Windows dead letter was ingested during the walkthrough to trigger the `DeadLettersIncreasing` rule.

### Replay from the console

![Replay](screenshots/13b-admin-replay.png)

Choosing **Use for replay** on a dead letter fills the source record id. On Linux the replay fails with `spawn py ENOENT`, because the route starts the Windows `py` launcher (README gap 5). `soc-ingest replay` works on every platform.

---

## Page guide

![Sentinel](screenshots/14-sentinel-guide.png)

Sentinel, the built-in page guide, open on the agent workspace in its light appearance. It explains the supervisor and each specialist, links to related pages the role may open, and states that it does not investigate, decide or call a model.

---

## API and metrics

### OpenAPI

![OpenAPI](screenshots/15-openapi-docs.png)

FastAPI's Swagger UI at `/docs`: the service description (roles, RLS, search, no authentication in this phase) and the operations grouped by tag.

### Search contract

![Search alerts](screenshots/15b-openapi-search-alerts.png)

`GET /api/v1/search/alerts` with every parameter, its type, limits and allowed values.

### Prometheus targets

![Targets](screenshots/16-prometheus-targets.png)

Prometheus scraping the API's `/metrics` and the relay's metrics port, both up.

### Alert rules

![Rules](screenshots/17-prometheus-alerts.png)

The repository's ten rules loaded from `/etc/prometheus/alerts.yml`. `DeadLettersIncreasing` is pending after a new dead letter, and `AgentRunFailures` after the failed and refused runs.

### Search rate

![Search rate](screenshots/18-prometheus-search-rate.png)

`sum by (operation) (rate(search_requests_total[5m]))` while a script exercised event, alert, entity and facet searches.
