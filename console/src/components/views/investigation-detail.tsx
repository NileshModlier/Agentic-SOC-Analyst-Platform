"use client";

import { useQuery, useQueries } from "@tanstack/react-query";
import Link from "next/link";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { formatTime } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

type TimelineItem = { at: string; title: string; detail: string; href?: string };

export function InvestigationDetailView({ id }: { id: string }) {
  const record = useQuery({ queryKey: ["investigation", id], queryFn: () => sdk.getInvestigation(id) });
  const alerts = useQueries({
    queries: (record.data?.alert_ids ?? []).map((alertId) => ({
      queryKey: ["alert", alertId],
      queryFn: () => sdk.getAlert(alertId),
    })),
  });
  const runs = useQueries({
    queries: (record.data?.alert_ids ?? []).map((alertId) => ({
      queryKey: ["runs", alertId],
      queryFn: () => sdk.listRuns({ alert_id: alertId, limit: 20 }),
    })),
  });

  if (record.isLoading) return <LoadingBlock label="Loading investigation" />;
  if (record.isError || !record.data) {
    return <ErrorState message={record.error instanceof ApiClientError ? record.error.message : "Investigation was not found."} onRetry={() => record.refetch()} />;
  }
  const item = record.data;
  const timeline: TimelineItem[] = [
    { at: item.opened_at, title: "Investigation opened", detail: item.hypothesis || "No hypothesis recorded." },
  ];
  for (const query of alerts) {
    if (!query.data) continue;
    timeline.push({
      at: query.data.detected_at,
      title: query.data.title,
      detail: `Linked alert · ${query.data.severity} · ${query.data.status}`,
      href: `/alerts/${query.data.id}`,
    });
  }
  for (const query of runs) {
    for (const run of query.data?.data ?? []) {
      timeline.push({
        at: run.created_at,
        title: run.draft_title || run.question || "Investigation run",
        detail: `${run.status} · requested by ${run.requested_by}`,
        href: `/agent-workspace?run=${run.id}`,
      });
    }
  }
  if (item.closed_at) timeline.push({ at: item.closed_at, title: "Investigation closed", detail: item.summary || "Closed." });
  timeline.sort((left, right) => new Date(left.at).getTime() - new Date(right.at).getTime());

  return (
    <div>
      <PageHeader title={item.title} detail="Timeline of the stored investigation, its linked alerts, and agent runs for those alerts." />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge value={item.status} />
        <span className="text-sm uppercase text-muted-foreground">{item.priority}</span>
        <span className="text-sm text-muted-foreground">{item.assignee || "Unassigned"}</span>
        {item.case_id ? <Link className="text-sm text-accent" href={`/cases/${item.case_id}`}>Open case</Link> : null}
      </div>
      {item.alert_ids.length === 0 ? (
        <div className="mb-4">
          <EmptyState title="No linked evidence" body="No alerts are linked to this investigation yet. The timeline below is the investigation record itself." />
        </div>
      ) : null}
      <section className="panel rounded-lg p-5">
        <ol className="relative ml-3 border-l border-border">
          {timeline.map((entry) => (
            <li key={`${entry.at}-${entry.title}`} className="mb-6 ml-6 last:mb-0">
              <span className="absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full bg-accent" />
              <p className="font-mono text-xs text-muted-foreground">{formatTime(entry.at)}</p>
              {entry.href ? (
                <Link className="font-medium text-accent" href={entry.href}>{entry.title}</Link>
              ) : (
                <p className="font-medium">{entry.title}</p>
              )}
              <p className="text-sm text-muted-foreground">{entry.detail}</p>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
