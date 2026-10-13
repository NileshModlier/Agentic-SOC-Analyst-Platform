import { NextResponse } from "next/server";

import { findOperator, isUuid } from "@/lib/operators";
import { sealSession, SESSION_COOKIE } from "@/lib/session-token";

export async function POST(request: Request) {
  let body: { operator?: string; password?: string; tenantId?: string };
  try {
    body = (await request.json()) as { operator?: string; password?: string; tenantId?: string };
  } catch {
    return NextResponse.json(
      { error: { code: "validation_error", message: "The request body is not valid JSON." } },
      { status: 422 },
    );
  }
  const tenantId = (body.tenantId || "").trim();
  const operator = findOperator((body.operator || "").trim(), body.password || "");
  if (!operator || !isUuid(tenantId)) {
    return NextResponse.json(
      { error: { code: "unauthenticated", message: "Operator, password, or tenant is not valid." } },
      { status: 401 },
    );
  }
  const token = await sealSession({
    sub: operator.id,
    role: operator.role,
    name: operator.name,
    tenantId,
    exp: Math.floor(Date.now() / 1000) + 60 * 60 * 12,
  });
  const response = NextResponse.json({ name: operator.name, role: operator.role, tenantId });
  response.cookies.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return response;
}
