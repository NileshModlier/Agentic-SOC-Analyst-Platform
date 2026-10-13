"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { formatTime } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

export function EntityDetailView({ id }: { id: string }) {
  const entity = useQuery({ queryKey: ["entity", id], queryFn: () => sdk.getEntity(id) });
  const alerts = useQuery({
    queryKey: ["entity-alerts", entity.data?.display_value],
    queryFn: () => sdk.searchAlerts({ q: entity.data?.display_value, limit: 20 }),
    enabled: Boolean(entity.data?.display_value),
  });
  const events = useQuery({
    queryKey: ["entity-events", entity.data?.display_value],
    queryFn: () => sdk.searchEvents({ q: entity.data?.display_value, limit: 20 }),
    enabled: Boolean(entity.data?.display_value),
  });

  if (entity.isLoading) return <LoadingBlock label="Loading entity" />;
  if (entity.isError || !entity.data) {
    return <ErrorState message={entity.error instanceof ApiClientError ? entity.error.message : "Entity was not found."} onRetry={() => entity.refetch()} />;
  }
  const row = entity.data;

  return (
    <div>
      <PageHeader title={row.display_value} detail={`${row.entity_type} catalog row. Related alerts and events are searches for this value, not a separate graph.`} />
      <div className="mb-4 flex flex-wrap gap-3 text-sm">
        <StatusBadge value={row.severity} />
        <span className="text-muted-foreground">{row.event_count} linked events</span>
        <span className="font-mono text-xs text-muted-foreground">First {formatTime(row.first_seen)} · Last {formatTime(row.last_seen)}</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <section className="panel rounded-lg p-4">
          <h2 className="mb-3 text-sm font-medium">Related alerts</h2>
          {alerts.isLoading ? <p className="text-sm text-muted-foreground">Loading alerts</p> : null}
          {alerts.data && alerts.data.data.length === 0 ? <EmptyState title="No alerts" body="No alert text matched this entity value." /> : null}
          <ul className="space-y-2">
            {(alerts.data?.data ?? []).map((alert) => (
              <li key={alert.id}>
                <Link className="block rounded border border-border p-3 hover:border-accent/40" href={`/alerts/${alert.id}`}>
                  <p className="font-medium">{alert.title}</p>
                  <p className="text-xs text-muted-foreground">{alert.severity} · {formatTime(alert.detected_at)}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
        <section className="panel rounded-lg p-4">
          <h2 className="mb-3 text-sm font-medium">Related events</h2>
          {events.isLoading ? <p className="text-sm text-muted-foreground">Loading events</p> : null}
          {events.data && events.data.data.length === 0 ? <EmptyState title="No events" body="No event text matched this entity value." /> : null}
          <ul className="space-y-2">
            {(events.data?.data ?? []).map((event) => {
              const hit = event as { id?: string; message?: string; event_time?: string; severity?: string };
              return (
                <li key={String(hit.id)} className="rounded border border-border p-3 text-sm">
                  <p>{String(hit.message || "Event")}</p>
                  <p className="text-xs text-muted-foreground">{String(hit.severity || "")} · {formatTime(String(hit.event_time || ""))}</p>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}
