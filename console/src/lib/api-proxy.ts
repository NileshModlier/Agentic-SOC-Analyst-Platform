import { NextResponse } from "next/server";

import { canReview } from "@/lib/operators";
import type { SessionClaims } from "@/lib/session-token";

const API = process.env.SOC_API_URL || "http://127.0.0.1:8000";

export function platformUrl(path: string[], request: Request, tenantId: string) {
  const incoming = new URL(request.url);
  const target = new URL(`${API}/${path.join("/")}`);
  incoming.searchParams.forEach((value, key) => {
    if (key !== "tenant") target.searchParams.append(key, value);
  });
  target.searchParams.set("tenant", tenantId);
  return target;
}

export async function readJson(request: Request) {
  const text = await request.text();
  if (!text) return {};
  return JSON.parse(text) as Record<string, unknown>;
}

export async function forward(target: URL, init: RequestInit) {
  try {
    const response = await fetch(target, { ...init, cache: "no-store" });
    const text = await response.text();
    return new Response(text, {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") || "application/json" },
    });
  } catch {
    return NextResponse.json(
      { error: { code: "api_unreachable", message: "The platform API is not reachable." } },
      { status: 502 },
    );
  }
}

export async function agentBody(path: string, body: Record<string, unknown>, session: SessionClaims) {
  const joined = path;
  if (joined === "api/v1/agent/runs") {
    return {
      alert_id: body.alert_id,
      question: body.question,
      requested_by: session.name,
    };
  }
  if (!joined.includes("/decisions")) return body;
  if (!canReview(session.role)) {
    throw NextResponse.json(
      { error: { code: "forbidden", message: "A reviewer decides investigation drafts." } },
      { status: 403 },
    );
  }
  const draftId = joined.split("/").at(-2);
  const draftUrl = new URL(`${API}/api/v1/agent/drafts/${draftId}`);
  draftUrl.searchParams.set("tenant", session.tenantId);
  const draftResponse = await fetch(draftUrl, { cache: "no-store" });
  if (!draftResponse.ok) {
    throw new Response(await draftResponse.text(), {
      status: draftResponse.status,
      headers: { "content-type": "application/json" },
    });
  }
  const draft = (await draftResponse.json()) as { run_id: string };
  const runUrl = new URL(`${API}/api/v1/agent/runs/${draft.run_id}`);
  runUrl.searchParams.set("tenant", session.tenantId);
  const runResponse = await fetch(runUrl, { cache: "no-store" });
  if (runResponse.ok) {
    const run = (await runResponse.json()) as { requested_by: string };
    if (run.requested_by === session.name) {
      throw NextResponse.json(
        {
          error: {
            code: "forbidden",
            message: "The person who requested the investigation cannot decide the draft.",
          },
        },
        { status: 403 },
      );
    }
  }
  const intent = body.intent;
  const note = typeof body.note === "string" ? body.note.trim() : "";
  if (intent === "request_changes") {
    if (!note) {
      throw NextResponse.json(
        { error: { code: "validation_error", message: "Request changes requires a note." } },
        { status: 422 },
      );
    }
    return { decision: "rejected", actor: session.name, note: `[changes-requested]\n${note}` };
  }
  const decision = body.decision === "approved" ? "approved" : body.decision === "rejected" ? "rejected" : null;
  if (!decision) {
    throw NextResponse.json(
      { error: { code: "validation_error", message: "Decision must be approved or rejected." } },
      { status: 422 },
    );
  }
  if (decision === "rejected" && !note) {
    throw NextResponse.json(
      { error: { code: "validation_error", message: "Reject requires a note." } },
      { status: 422 },
    );
  }
  return { decision, actor: session.name, note: note || null };
}

export function denied(message: string, status = 403) {
  return NextResponse.json({ error: { code: status === 401 ? "unauthenticated" : "forbidden", message } }, { status });
}
