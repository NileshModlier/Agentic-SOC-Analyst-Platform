"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { Pager } from "@/components/pager";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { formatTime } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

const TYPES = [
  ["user", "Users"],
  ["host", "Hosts"],
  ["process", "Processes"],
  ["file", "Files"],
  ["ip", "IPs"],
] as const;

export function EntitiesView() {
  return (
    <Suspense fallback={<LoadingBlock label="Loading entities" />}>
      <EntitiesExplorer />
    </Suspense>
  );
}

function EntitiesExplorer() {
  const router = useRouter();
  const search = useSearchParams();
  const type = TYPES.some(([value]) => value === search.get("type")) ? search.get("type") || "user" : "user";
  const initialQuery = search.get("q") || "";
  const [q, setQ] = useState(initialQuery);
  const [sort, setSort] = useState("event_time");
  const [cursors, setCursors] = useState<string[]>([]);
  const cursor = cursors.at(-1);
  const rows = useQuery({
    queryKey: ["entities", type, q, sort, cursor],
    queryFn: () => sdk.searchEntities({ entity_type: type, q, sort, limit: 25, cursor }),
  });

  function chooseType(next: string) {
    setCursors([]);
    const params = new URLSearchParams(search.toString());
    params.set("type", next);
    router.replace(`/entities?${params.toString()}`);
  }

  return (
    <div>
      <PageHeader
        title="Entity explorer"
        detail="One catalog for users, hosts, processes, files, and IP addresses observed in events."
      />
      <div className="mb-4 flex flex-wrap gap-2">
        {TYPES.map(([value, name]) => (
          <button
            key={value}
            className={`rounded-md px-3 py-1.5 text-sm ${type === value ? "bg-accent text-accent-foreground" : "border border-border text-muted-foreground"}`}
            onClick={() => chooseType(value)}
          >
            {name}
          </button>
        ))}
      </div>
      <div className="mb-4 flex gap-2">
        <input className="field max-w-md" placeholder={`Search ${type}s`} value={q} onChange={(event) => { setQ(event.target.value); setCursors([]); }} />
        <select className="field max-w-[200px]" value={sort} onChange={(event) => { setSort(event.target.value); setCursors([]); }}>
          <option value="event_time">Last seen</option>
          <option value="created_time">First seen</option>
          <option value="severity">Severity</option>
        </select>
      </div>
      {rows.isLoading ? <LoadingBlock label="Loading entities" /> : null}
      {rows.isError ? <ErrorState message={rows.error instanceof ApiClientError ? rows.error.message : "Entities could not be loaded."} onRetry={() => rows.refetch()} /> : null}
      {rows.data && rows.data.data.length === 0 ? (
        <EmptyState
          title="No matching entities were found."
          body={`No ${type} records match this search. Try another value, or switch among users, hosts, processes, files, and IP addresses.`}
        />
      ) : null}
      {rows.data && rows.data.data.length > 0 ? (
        <div className="panel overflow-hidden rounded-lg">
          <table className="data-table">
            <thead>
              <tr>
                <th>Value</th>
                <th>Severity</th>
                <th>Events</th>
                <th>First seen</th>
                <th>Last seen</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.data.map((entity) => (
                <tr key={entity.id} onClick={() => router.push(`/entities/${entity.id}`)}>
                  <td>
                    <p className="font-medium">{entity.display_value}</p>
                    <p className="font-mono text-xs text-muted-foreground">{entity.entity_type}</p>
                  </td>
                  <td><StatusBadge value={entity.severity} /></td>
                  <td className="font-mono">{entity.event_count}</td>
                  <td className="font-mono text-xs">{formatTime(entity.first_seen)}</td>
                  <td className="font-mono text-xs">{formatTime(entity.last_seen)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {rows.data ? (
        <Pager
          page={cursors.length + 1}
          hasPrevious={cursors.length > 0}
          hasNext={rows.data.page.has_more}
          onPrevious={() => setCursors((items) => items.slice(0, -1))}
          onNext={() => rows.data?.page.next_cursor && setCursors((items) => [...items, rows.data?.page.next_cursor || ""])}
        />
      ) : null}
    </div>
  );
}
