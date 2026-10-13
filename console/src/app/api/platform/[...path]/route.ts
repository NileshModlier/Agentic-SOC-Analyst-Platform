import { cookies } from "next/headers";

import { agentBody, forward, platformUrl, readJson } from "@/lib/api-proxy";
import { openSession, SESSION_COOKIE } from "@/lib/session-token";

async function sessionOr401() {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = await openSession(token);
  if (!session) {
    return {
      session: null,
      response: Response.json(
        { error: { code: "unauthenticated", message: "Sign in required." } },
        { status: 401 },
      ),
    };
  }
  return { session, response: null };
}

async function proxy(request: Request, path: string[], method: "GET" | "POST") {
  const { session, response } = await sessionOr401();
  if (!session || response) return response;
  const target = platformUrl(path, request, session.tenantId);
  if (method === "GET") return forward(target, { method: "GET" });
  let body: Record<string, unknown> = {};
  try {
    body = await readJson(request);
    body = await agentBody(path.join("/"), body, session);
  } catch (error) {
    if (error instanceof Response) return error;
    return Response.json(
      { error: { code: "validation_error", message: "The request body is not valid JSON." } },
      { status: 422 },
    );
  }
  return forward(target, { method: "POST", body: JSON.stringify(body), headers: { "content-type": "application/json" } });
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxy(request, path, "GET");
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxy(request, path, "POST");
}
