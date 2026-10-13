"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { formatTime, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";

export function ReviewsView() {
  const [selected, setSelected] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const client = useQueryClient();
  const queue = useQuery({
    queryKey: ["reviews", "pending"],
    queryFn: () => sdk.listDrafts({ status: "pending_approval", limit: 50 }),
  });
  const decided = useQuery({
    queryKey: ["reviews", "decided"],
    queryFn: () => sdk.listDrafts({ limit: 20 }),
  });
  const draft = useQuery({
    queryKey: ["draft", selected],
    queryFn: () => sdk.getDraft(selected),
    enabled: Boolean(selected),
  });
  const decide = useMutation({
    mutationFn: (body: { decision: "approved" | "rejected"; note?: string; intent?: "request_changes" }) =>
      sdk.decide(selected, body),
    onSuccess: async () => {
      setError("");
      setNote("");
      await client.invalidateQueries({ queryKey: ["reviews"] });
      await client.invalidateQueries({ queryKey: ["draft", selected] });
      await client.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (reason) => setError(reason instanceof ApiClientError ? reason.message : "The decision was not recorded."),
  });

  const history = (decided.data?.data ?? []).filter((item) => item.approval);

  return (
    <div>
      <PageHeader
        title="Review queue"
        detail="A reviewer approves, rejects, or requests changes. Request changes records a rejection with your note. No canonical record is changed."
      />
      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <section className="panel rounded-lg p-3">
          <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Pending approval</p>
          {queue.isLoading ? <LoadingBlock label="Loading reviews" /> : null}
          {queue.isError ? <ErrorState message={queue.error instanceof ApiClientError ? queue.error.message : "The queue could not be loaded."} onRetry={() => queue.refetch()} /> : null}
          {queue.data && queue.data.data.length === 0 ? <EmptyState title="Queue is clear" body="No draft is waiting for a person." /> : null}
          <ul className="space-y-1">
            {(queue.data?.data ?? []).map((item) => (
              <li key={item.id}>
                <button className={`w-full rounded px-2 py-2 text-left text-sm hover:bg-white/5 ${selected === item.id ? "bg-accent/10" : ""}`} onClick={() => setSelected(item.id)}>
                  <span className="block truncate">{item.title}</span>
                  <span className="text-xs text-muted-foreground">{label(item.severity)} · {formatTime(item.created_at)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section>
          {!selected ? <EmptyState title="Select a draft" body="Open a pending draft to read its claims and record a decision." /> : null}
          {draft.isLoading ? <LoadingBlock label="Loading draft" /> : null}
          {draft.data ? (
            <div className="panel rounded-lg p-4">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-sm font-medium">{draft.data.title}</h2>
                <StatusBadge value={draft.data.status} />
                <StatusBadge value={draft.data.severity} />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{draft.data.notice}</p>
              <p className="mt-3 text-sm">{draft.data.summary}</p>
              <ol className="mt-4 space-y-2">
                {draft.data.claims.map((claim) => (
                  <li key={claim.position} className="rounded border border-border p-3 text-sm">
                    <p>{claim.statement}</p>
                    <p className="mt-1 font-mono text-xs text-muted-foreground">
                      {claim.citations.map((citation) => `${citation.kind}:${citation.record_id.slice(0, 8)}`).join(" · ") || "No citation"}
                    </p>
                  </li>
                ))}
              </ol>
              {draft.data.status === "pending_approval" ? (
                <div className="mt-4">
                  <textarea className="field h-20 py-2" placeholder="Note for a rejection or a change request" value={note} onChange={(event) => setNote(event.target.value)} />
                  {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button disabled={decide.isPending} onClick={() => decide.mutate({ decision: "approved", note })}>Approve</Button>
                    <Button variant="danger" disabled={decide.isPending} onClick={() => decide.mutate({ decision: "rejected", note })}>Reject</Button>
                    <Button variant="secondary" disabled={decide.isPending} onClick={() => decide.mutate({ decision: "rejected", intent: "request_changes", note })}>Request changes</Button>
                  </div>
                </div>
              ) : draft.data.approval ? (
                <p className="mt-4 text-sm text-muted-foreground">
                  {decisionLabel(draft.data.approval.decision, draft.data.approval.note)} by {draft.data.approval.actor} · {formatTime(draft.data.approval.created_at)}
                  {draft.data.approval.note ? ` · ${visibleNote(draft.data.approval.note)}` : ""}
                </p>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
      <section className="mt-6">
        <h2 className="mb-3 text-sm font-medium">Recent decisions</h2>
        {history.length === 0 ? <EmptyState title="No decisions" body="Approved and rejected drafts appear here." /> : null}
        {history.length > 0 ? (
          <div className="panel overflow-hidden rounded-lg">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Draft</th>
                  <th>Decision</th>
                  <th>Actor</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id} onClick={() => setSelected(item.id)}>
                    <td>{item.title}</td>
                    <td>{decisionLabel(item.approval?.decision, item.approval?.note)}</td>
                    <td>{item.approval?.actor}</td>
                    <td className="font-mono text-xs">{formatTime(item.approval?.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function decisionLabel(decision: string | undefined, note: string | null | undefined) {
  if (note?.startsWith("[changes-requested]")) return "Changes requested";
  if (decision === "approved") return "Approved";
  if (decision === "rejected") return "Rejected";
  return "Decided";
}

function visibleNote(note: string) {
  return note.replace(/^\[changes-requested]\n?/, "");
}
