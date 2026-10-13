"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { formatTime, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

const STATUSES = ["", "open", "investigating", "contained", "recovered", "closed"];

export function CasesView() {
  const router = useRouter();
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1);
  const cases = useQuery({
    queryKey: ["cases", status, severity, cursor],
    queryFn: () => sdk.listCases({ case_status: status, severity, limit: 25, cursor }),
  });

  return (
    <div>
      <PageHeader
        title="Case management"
        detail="Incident containers already stored for this tenant. This console reads case status and linked work. It does not change a case."
      />
      <div className="mb-4 flex gap-2">
        <select className="field max-w-xs" value={status} onChange={(event) => { setStatus(event.target.value); setCursors([]); }}>
          {STATUSES.map((item) => <option key={item || "all"} value={item}>{item ? label(item) : "All statuses"}</option>)}
        </select>
        <select className="field max-w-xs" value={severity} onChange={(event) => { setSeverity(event.target.value); setCursors([]); }}>
          {["", "critical", "high", "medium", "low", "informational", "unknown"].map((item) => (
            <option key={item || "all"} value={item}>{item ? label(item) : "All severities"}</option>
          ))}
        </select>
      </div>
      {cases.isLoading ? <LoadingBlock label="Loading cases" /> : null}
      {cases.isError ? <ErrorState message={cases.error instanceof ApiClientError ? cases.error.message : "Cases could not be loaded."} onRetry={() => cases.refetch()} /> : null}
      {cases.data && cases.data.data.length === 0 ? (
        <EmptyState
          title="No cases"
          body={status || severity ? "No cases match this filter. Case status moves from open to investigating, contained, recovered, and closed." : "No cases have been opened yet."}
        />
      ) : null}
      {cases.data && cases.data.data.length > 0 ? (
        <div className="panel overflow-hidden rounded-lg">
          <table className="data-table">
            <thead>
              <tr>
                <th>Case</th>
                <th>Status</th>
                <th>Severity</th>
                <th>Assignee</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {cases.data.data.map((item) => (
                <tr key={item.id} onClick={() => router.push(`/cases/${item.id}`)}>
                  <td>
                    <p className="font-medium">{item.title}</p>
                    <p className="text-xs text-muted-foreground">{item.external_ref || "No external reference"}</p>
                  </td>
                  <td><StatusBadge value={item.status} /></td>
                  <td><StatusBadge value={item.severity} /></td>
                  <td>{item.assignee || "Unassigned"}</td>
                  <td className="font-mono text-xs">{formatTime(item.opened_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {cases.data ? (
        <Pager
          page={cursors.length + 1}
          hasPrevious={cursors.length > 0}
          hasNext={cases.data.page.has_more}
          onPrevious={() => setCursors((items) => items.slice(0, -1))}
          onNext={() => cases.data?.page.next_cursor && setCursors((items) => [...items, cases.data?.page.next_cursor || ""])}
        />
      ) : null}
    </div>
  );
}
