"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/severity";
import { EmptyState, ErrorState, LoadingBlock } from "@/components/states";
import { Button } from "@/components/ui/button";
import { formatTime, label } from "@/lib/format";
import { ApiClientError, sdk } from "@/lib/sdk/client";
import type { Citation, Draft, Run } from "@/lib/sdk/types";

const VALIDATION: Record<string, string> = {
  pending_approval: "Every stored claim matched a reloaded record. A reviewer still has to decide the draft.",
  validation_failed: "At least one claim did not match the stored record. The draft cannot be approved.",
  insufficient_evidence: "The workflow did not produce a citable claim.",
  approved: "A person approved the draft. Canonical records were not changed.",
  rejected: "A person rejected the draft. Canonical records were not changed.",
};

export function WorkspaceView() {
  return (
    <Suspense fallback={<LoadingBlock label="Loading workspace" />}>
      <Workspace />
    </Suspense>
  );
}

function Workspace() {
  const search = useSearchParams();
  const router = useRouter();
  const client = useQueryClient();
  const [alertId, setAlertId] = useState(search.get("alert") || "");
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const selected = search.get("run") || "";
  const runs = useQuery({ queryKey: ["workspace-runs"], queryFn: () => sdk.listRuns({ limit: 20 }) });
  const run = useQuery({ queryKey: ["run", selected], queryFn: () => sdk.getRun(selected), enabled: Boolean(selected) });
  const start = useMutation({
    mutationFn: () => sdk.startRun(alertId.trim() ? { alert_id: alertId.trim() } : { question: question.trim() }),
    onSuccess: async (created) => {
      setError("");
      await client.invalidateQueries({ queryKey: ["workspace-runs"] });
      router.replace(`/agent-workspace?run=${created.id}`);
    },
    onError: (reason) => setError(reason instanceof ApiClientError ? reason.message : "The investigation did not start."),
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!alertId.trim() && !question.trim()) {
      setError("Provide an alert id or a question.");
      return;
    }
    start.mutate();
  }

  return (
    <div>
      <PageHeader
        title="Agent workspace"
        detail="Start a local investigation. The draft cites stored records and is not a source of truth. There is no chat."
      />
      <div className="grid gap-4 xl:grid-cols-[320px_1fr]">
        <section className="space-y-4">
          <form className="panel rounded-lg p-4" onSubmit={submit}>
            <h2 className="text-sm font-medium">Run investigation</h2>
            <label className="mt-3 block text-xs text-muted-foreground">
              Alert id
              <input className="field mt-1 font-mono" value={alertId} onChange={(event) => setAlertId(event.target.value)} />
            </label>
            <label className="mt-3 block text-xs text-muted-foreground">
              Or a question about stored records
              <textarea className="field mt-1 h-20 py-2" value={question} onChange={(event) => setQuestion(event.target.value)} />
            </label>
            {error ? <p className="mt-2 text-sm text-danger">{error}</p> : null}
            <Button className="mt-3 w-full" disabled={start.isPending} type="submit">
              {start.isPending ? "Running" : "Run investigation"}
            </Button>
          </form>
          <div className="panel rounded-lg p-3">
            <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Recent runs</p>
            {runs.isLoading ? <p className="text-sm text-muted-foreground">Loading runs</p> : null}
            {runs.data && runs.data.data.length === 0 ? <p className="text-sm text-muted-foreground">No investigations have been started from this workspace yet. A run drafts cited claims. A person approves or rejects that draft.</p> : null}
            <ul className="space-y-1">
              {(runs.data?.data ?? []).map((item) => (
                <li key={item.id}>
                  <button
                    className={`w-full rounded px-2 py-2 text-left text-sm hover:bg-white/5 ${selected === item.id ? "bg-accent/10" : ""}`}
                    onClick={() => router.replace(`/agent-workspace?run=${item.id}`)}
                  >
                    <span className="block truncate">{item.draft_title || item.question || item.alert_id || "Run"}</span>
                    <span className="text-xs text-muted-foreground">{label(item.status)} · {formatTime(item.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </section>
        <section>
          {!selected ? <EmptyState title="No run selected" body="Start an investigation or choose a recent run." /> : null}
          {run.isLoading ? <LoadingBlock label="Loading run" /> : null}
          {run.isError ? <ErrorState message={run.error instanceof ApiClientError ? run.error.message : "The run could not be loaded."} onRetry={() => run.refetch()} /> : null}
          {run.data ? <RunPanels run={run.data} /> : null}
        </section>
      </div>
    </div>
  );
}

function RunPanels({ run }: { run: Run }) {
  const draft = run.draft;
  return (
    <div className="space-y-4">
      <section className="panel rounded-lg p-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-medium">{draft?.title || "Investigation run"}</h2>
          <StatusBadge value={run.status} />
          {draft ? <StatusBadge value={draft.status} /> : null}
        </div>
        <p className="mt-2 text-sm text-muted-foreground">Requested by {run.requested_by} · {formatTime(run.created_at)}</p>
        {run.error_message ? <p className="mt-2 text-sm text-danger">{run.error_code}: {run.error_message}</p> : null}
        {draft ? <p className="mt-3 text-sm">{draft.notice}</p> : null}
      </section>
      <section className="panel rounded-lg p-4">
        <h2 className="text-sm font-medium">Validation</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {draft ? VALIDATION[draft.status] || draft.summary : "Reporting did not store a draft."}
        </p>
        {draft?.summary ? <p className="mt-2 text-sm">{draft.summary}</p> : null}
      </section>
      <section className="panel rounded-lg p-4">
        <h2 className="text-sm font-medium">Draft</h2>
        {!draft || draft.claims.length === 0 ? <p className="mt-2 text-sm text-muted-foreground">No claims were stored.</p> : null}
        <ol className="mt-3 space-y-3">
          {(draft?.claims ?? []).map((claim) => (
            <li key={claim.position} className="rounded border border-border p-3">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">{claim.template}</p>
              <p className="mt-1 text-sm">{claim.statement}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {claim.citations.map((citation) => (
                  <CitationLink key={`${citation.kind}-${citation.record_id}`} citation={citation} />
                ))}
              </div>
            </li>
          ))}
        </ol>
      </section>
      {draft ? <EvidenceView draft={draft} /> : null}
      <section className="panel rounded-lg p-4">
        <h2 className="mb-3 text-sm font-medium">Agent memory</h2>
        <ol className="space-y-2">
          {run.memory.map((item) => (
            <li key={item.sequence} className="rounded border border-border px-3 py-2 text-sm">
              <span className="font-mono text-xs text-muted-foreground">{item.sequence}</span> {label(item.agent)} · {label(item.kind)}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function CitationLink({ citation }: { citation: Citation }) {
  const href =
    citation.kind === "alert"
      ? `/alerts/${citation.record_id}`
      : citation.kind === "entity"
        ? `/entities/${citation.record_id}`
        : undefined;
  const text = `${citation.kind} ${citation.record_id.slice(0, 8)}`;
  if (!href) return <span className="font-mono text-xs text-muted-foreground">{text}</span>;
  return <a className="font-mono text-xs text-accent" href={href}>{text}</a>;
}

function EvidenceView({ draft }: { draft: Draft }) {
  const evidence = draft.claims.flatMap((claim) => claim.citations).filter((citation) => citation.kind === "evidence");
  const unique = [...new Map(evidence.map((item) => [item.record_id, item])).values()];
  return (
    <section className="panel rounded-lg p-4">
      <h2 className="text-sm font-medium">Evidence</h2>
      <p className="mt-1 text-xs text-muted-foreground">Custody metadata for cited evidence. Raw source bytes are not shown.</p>
      {unique.length === 0 ? <p className="mt-3 text-sm text-muted-foreground">This draft cites no evidence record.</p> : null}
      <div className="mt-3 space-y-3">
        {unique.map((citation) => (
          <EvidenceCard key={citation.record_id} id={citation.record_id} />
        ))}
      </div>
    </section>
  );
}

function EvidenceCard({ id }: { id: string }) {
  const record = useQuery({ queryKey: ["evidence", id], queryFn: () => sdk.getEvidence(id) });
  if (record.isLoading) return <p className="text-sm text-muted-foreground">Loading evidence</p>;
  if (record.isError || !record.data) return <p className="text-sm text-danger">Evidence {id.slice(0, 8)} could not be loaded.</p>;
  const item = record.data;
  return (
    <div className="rounded border border-border p-3 text-sm">
      <p>{item.description}</p>
      <p className="mt-1 text-xs text-muted-foreground">{label(item.evidence_type)} · {item.byte_size} bytes · {item.collected_by}</p>
      <p className="mt-1 break-all font-mono text-xs text-muted-foreground">{item.content_sha256}</p>
      <p className="mt-1 font-mono text-xs text-muted-foreground">{formatTime(item.collected_at)}</p>
    </div>
  );
}
