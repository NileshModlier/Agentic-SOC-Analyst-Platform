"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { formatTime, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";
import type { FacetBucket } from "@/lib/sdk/types";

const SOURCES = ["", "sigma_alert", "mock_edr_alert", "windows_event"];
const SEVERITIES = ["", "critical", "high", "medium", "low", "informational", "unknown"];
const STATUSES = ["", "new", "in_review", "closed", "suppressed"];
const SORTS = [
  ["event_time", "Detection time"],
  ["severity", "Severity"],
  ["created_time", "Created time"],
];

export function AlertsView() {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [severity, setSeverity] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [eventType, setEventType] = useState("");
  const [sort, setSort] = useState("event_time");
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1);

  const params = useMemo(
    () => ({ q, severity, source, status, event_type: eventType, sort, limit: 25, cursor }),
    [q, severity, source, status, eventType, sort, cursor],
  );
  const alerts = useQuery({ queryKey: ["alerts", params], queryFn: () => sdk.searchAlerts(params) });
  const facets = useQuery({
    queryKey: ["alert-facets", { q, severity, source, eventType }],
    queryFn: () => sdk.facets({ q, severity, source, event_type: eventType }),
  });

  function resetPage() {
    setCursors([]);
  }

  return (
    <div>
      <PageHeader
        title="Alert explorer"
        detail="Search detections in this tenant. Facets count the event corpus and omit their own filter. Sorting and pages stay on the alert index."
      />
      <div className="mb-4 grid gap-2 md:grid-cols-6">
        <input className="field md:col-span-2" placeholder="Search alerts" value={q} onChange={(event) => { setQ(event.target.value); resetPage(); }} />
        <Select value={severity} onChange={(value) => { setSeverity(value); resetPage(); }} options={SEVERITIES} placeholder="Severity" />
        <Select value={source} onChange={(value) => { setSource(value); resetPage(); }} options={SOURCES} placeholder="Source" />
        <Select value={status} onChange={(value) => { setStatus(value); resetPage(); }} options={STATUSES} placeholder="Status" />
        <select className="field" value={sort} onChange={(event) => { setSort(event.target.value); resetPage(); }}>
          {SORTS.map(([value, name]) => (
            <option key={value} value={value}>{name}</option>
          ))}
        </select>
      </div>
      <div className="grid gap-4 lg:grid-cols-[240px_1fr]">
        <aside className="space-y-4">
          <FacetGroup title="Severity" buckets={facets.data?.severity} active={severity} onPick={(value) => { setSeverity(value === severity ? "" : value); resetPage(); }} />
          <FacetGroup title="Source" buckets={facets.data?.source} active={source} onPick={(value) => { setSource(value === source ? "" : value); resetPage(); }} />
          <FacetGroup title="Event type" buckets={facets.data?.event_type} active={eventType} onPick={(value) => { setEventType(value === eventType ? "" : value); resetPage(); }} />
          <FacetGroup title="Host" buckets={facets.data?.host} active="" onPick={(value) => router.push(`/entities?type=host&q=${encodeURIComponent(value)}`)} />
          <FacetGroup title="User" buckets={facets.data?.user} active="" onPick={(value) => router.push(`/entities?type=user&q=${encodeURIComponent(value)}`)} />
        </aside>
        <section>
          {alerts.isLoading ? <LoadingBlock label="Loading alerts" /> : null}
          {alerts.isError ? (
            <ErrorState message={alerts.error instanceof ApiClientError ? alerts.error.message : "Alerts could not be loaded."} onRetry={() => alerts.refetch()} />
          ) : null}
          {alerts.data && alerts.data.data.length === 0 ? (
            <EmptyState title="No alerts" body="No detections match this search. Clear severity, status, source, or the search text. Facets count the event corpus and leave out their own filter." />
          ) : null}
          {alerts.data && alerts.data.data.length > 0 ? (
            <div className="panel overflow-hidden rounded-lg">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Alert</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Host</th>
                    <th>Detected</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.data.data.map((alert) => (
                    <tr key={alert.id} onClick={() => router.push(`/alerts/${alert.id}`)}>
                      <td>
                        <p className="font-medium">{alert.title}</p>
                        <p className="text-xs text-muted-foreground">{label(alert.source)} · {alert.rule_name || "no rule name"}</p>
                      </td>
                      <td><StatusBadge value={alert.severity} /></td>
                      <td><StatusBadge value={alert.status} /></td>
                      <td>{alert.hostname || "—"}</td>
                      <td className="whitespace-nowrap font-mono text-xs">{formatTime(alert.detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {alerts.data ? (
            <Pager
              page={cursors.length + 1}
              hasPrevious={cursors.length > 0}
              hasNext={alerts.data.page.has_more}
              onPrevious={() => setCursors((items) => items.slice(0, -1))}
              onNext={() => {
                if (alerts.data?.page.next_cursor) setCursors((items) => [...items, alerts.data.page.next_cursor || ""]);
              }}
            />
          ) : null}
        </section>
      </div>
    </div>
  );
}

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  placeholder: string;
}) {
  return (
    <select className="field" value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option || "all"} value={option}>{option ? label(option) : `All ${placeholder.toLowerCase()}`}</option>
      ))}
    </select>
  );
}

function FacetGroup({
  title,
  buckets,
  active,
  onPick,
}: {
  title: string;
  buckets?: FacetBucket[];
  active: string;
  onPick: (value: string) => void;
}) {
  return (
    <div className="panel rounded-lg p-3">
      <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">{title}</p>
      {!buckets ? <p className="text-xs text-muted-foreground">Loading</p> : null}
      {buckets && buckets.length === 0 ? <p className="text-xs text-muted-foreground">None</p> : null}
      <div className="space-y-1">
        {(buckets ?? []).map((bucket) => (
          <Button
            key={bucket.value}
            variant="ghost"
            size="sm"
            className={`w-full justify-between ${active === bucket.value ? "text-accent" : ""}`}
            onClick={() => onPick(bucket.value)}
          >
            <span className="truncate">{bucket.value}</span>
            <span className="font-mono text-xs">{bucket.count}</span>
          </Button>
        ))}
      </div>
    </div>
  );
}
