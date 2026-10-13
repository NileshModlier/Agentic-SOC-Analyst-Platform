"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { formatTime, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

export function AdminView() {
  const client = useQueryClient();
  const [sourceRecordId, setSourceRecordId] = useState("");
  const [replayMessage, setReplayMessage] = useState("");
  const connectors = useQuery({ queryKey: ["admin", "connectors"], queryFn: () => sdk.connectors() });
  const letters = useQuery({ queryKey: ["admin", "dead-letters"], queryFn: () => sdk.deadLetters({ limit: 50 }) });
  const publications = useQuery({ queryKey: ["admin", "publications"], queryFn: () => sdk.publications({ limit: 50 }) });
  const decisions = useQuery({ queryKey: ["admin", "decisions"], queryFn: () => sdk.listDrafts({ limit: 50 }) });
  const replay = useMutation({
    mutationFn: async () => {
      const response = await fetch("/api/operations/replay", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ sourceRecordId }),
      });
      const body = (await response.json()) as { error?: { message?: string }; receipt_status?: string; source_record_id?: string };
      if (!response.ok) throw new ApiClientError(response.status, body.error?.message || "replay_failed", body.error?.message || "Replay failed.");
      return body;
    },
    onSuccess: async (body) => {
      setReplayMessage(`Replay finished with receipt ${body.receipt_status || "recorded"} for ${body.source_record_id}.`);
      await client.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (reason) => setReplayMessage(reason instanceof Error ? reason.message : "Replay failed."),
  });

  const audit = (decisions.data?.data ?? []).filter((item) => item.approval);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Administration"
        detail="Connector receipts, dead-letter metadata, replay of stored bytes, and the human decision record. Payloads are not shown."
      />
      <section>
        <h2 className="mb-3 text-sm font-medium">Connector health</h2>
        {connectors.isLoading ? <LoadingBlock label="Loading connectors" /> : null}
        {connectors.isError ? <ErrorState message={connectors.error instanceof ApiClientError ? connectors.error.message : "Connectors could not be loaded."} onRetry={() => connectors.refetch()} /> : null}
        <div className="grid gap-3 md:grid-cols-3">
          {(connectors.data?.data ?? []).map((connector) => (
            <article key={connector.source} className="panel rounded-lg p-4">
              <p className="text-sm font-medium">{connector.label}</p>
              <p className="mt-2 font-mono text-2xl">{connector.projected}</p>
              <p className="text-xs text-muted-foreground">Projected receipts</p>
              <p className="mt-3 text-sm">{connector.dead_lettered} dead-lettered</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">Last intake {formatTime(connector.last_received_at)}</p>
            </article>
          ))}
        </div>
      </section>
      <section className="panel rounded-lg p-4">
        <h2 className="text-sm font-medium">Replay</h2>
        <p className="mt-1 text-sm text-muted-foreground">Re-project one source record from the bytes stored at intake. This does not accept a new payload.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <input className="field max-w-lg font-mono" placeholder="source record id" value={sourceRecordId} onChange={(event) => setSourceRecordId(event.target.value)} />
          <Button disabled={replay.isPending || !sourceRecordId.trim()} onClick={() => replay.mutate()}>
            {replay.isPending ? "Replaying" : "Replay stored bytes"}
          </Button>
        </div>
        {replayMessage ? <p className="mt-2 text-sm text-muted-foreground">{replayMessage}</p> : null}
      </section>
      <section>
        <h2 className="mb-3 text-sm font-medium">Dead letters</h2>
        {letters.isLoading ? <LoadingBlock label="Loading dead letters" /> : null}
        {letters.isError ? <ErrorState message={letters.error instanceof ApiClientError ? letters.error.message : "Dead letters could not be loaded."} onRetry={() => letters.refetch()} /> : null}
        {letters.data && letters.data.data.length === 0 ? <EmptyState title="No dead letters" body="Parse, publish, and replay failures will appear here." /> : null}
        {letters.data && letters.data.data.length > 0 ? (
          <div className="panel overflow-hidden rounded-lg">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Reason</th>
                  <th>Attempts</th>
                  <th>Created</th>
                  <th>Resolved</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {letters.data.data.map((item) => (
                  <tr key={item.id} onClick={() => item.source_record_id && setSourceRecordId(item.source_record_id)}>
                    <td><StatusBadge value={item.stage} /></td>
                    <td>
                      <p>{item.reason_code}</p>
                      <p className="max-w-md text-xs text-muted-foreground">{item.error_message}</p>
                    </td>
                    <td className="font-mono">{item.attempt_count}</td>
                    <td className="font-mono text-xs">{formatTime(item.created_at)}</td>
                    <td className="font-mono text-xs">{formatTime(item.resolved_at)}</td>
                    <td>{item.source_record_id ? <Button size="sm" variant="secondary">Use for replay</Button> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
      <section>
        <h2 className="mb-3 text-sm font-medium">Audit</h2>
        <div className="grid gap-4 lg:grid-cols-2">
          <div>
            <h3 className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Human decisions</h3>
            {audit.length === 0 ? <EmptyState title="No decisions" body="Draft approvals and rejections are the human audit record." /> : null}
            {audit.length > 0 ? (
              <div className="panel overflow-hidden rounded-lg">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Draft</th>
                      <th>Decision</th>
                      <th>Actor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((item) => (
                      <tr key={item.id}>
                        <td>{item.title}</td>
                        <td>{item.approval?.note?.startsWith("[changes-requested]") ? "Changes requested" : label(item.approval?.decision)}</td>
                        <td>{item.approval?.actor}<br /><span className="font-mono text-xs text-muted-foreground">{formatTime(item.approval?.created_at)}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
          <div>
            <h3 className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Publications</h3>
            {publications.isLoading ? <LoadingBlock label="Loading publications" /> : null}
            {publications.data && publications.data.data.length === 0 ? <EmptyState title="No publications" body="Outbox delivery status appears after intake." /> : null}
            {publications.data && publications.data.data.length > 0 ? (
              <div className="panel overflow-hidden rounded-lg">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Event</th>
                      <th>Status</th>
                      <th>When</th>
                    </tr>
                  </thead>
                  <tbody>
                    {publications.data.data.map((item) => (
                      <tr key={item.id}>
                        <td>{item.event_type}<br /><span className="text-xs text-muted-foreground">{item.aggregate_type}</span></td>
                        <td><StatusBadge value={item.status} /></td>
                        <td className="font-mono text-xs">{formatTime(item.published_at || item.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}
