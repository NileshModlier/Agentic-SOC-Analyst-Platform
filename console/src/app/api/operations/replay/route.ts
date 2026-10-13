import { spawn } from "node:child_process";
import path from "node:path";

import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { canAdminister, isUuid } from "@/lib/operators";
import { openSession, SESSION_COOKIE } from "@/lib/session-token";

export async function POST(request: Request) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = await openSession(token);
  if (!session) {
    return NextResponse.json({ error: { code: "unauthenticated", message: "Sign in required." } }, { status: 401 });
  }
  if (!canAdminister(session.role)) {
    return NextResponse.json(
      { error: { code: "forbidden", message: "Replay is limited to the administrator role." } },
      { status: 403 },
    );
  }
  let body: { sourceRecordId?: string };
  try {
    body = (await request.json()) as { sourceRecordId?: string };
  } catch {
    return NextResponse.json(
      { error: { code: "validation_error", message: "The request body is not valid JSON." } },
      { status: 422 },
    );
  }
  const sourceRecordId = (body.sourceRecordId || "").trim();
  if (!isUuid(sourceRecordId)) {
    return NextResponse.json(
      { error: { code: "validation_error", message: "A source record id is required." } },
      { status: 422 },
    );
  }
  const result = await runReplay(session.tenantId, sourceRecordId);
  if (result.stdout.startsWith("{")) {
    return NextResponse.json(JSON.parse(result.stdout) as unknown, { status: result.code === 0 || result.code === 2 ? 200 : 422 });
  }
  return NextResponse.json(
    { error: { code: "replay_failed", message: result.stderr || "Replay did not complete." } },
    { status: 422 },
  );
}

function runReplay(tenantId: string, sourceRecordId: string) {
  return new Promise<{ code: number; stdout: string; stderr: string }>((resolve) => {
    const child = spawn(
      "py",
      ["-3", "-m", "soc_platform.cli", "replay", "--tenant", tenantId, "--source-record", sourceRecordId],
      {
        cwd: path.resolve(process.cwd(), ".."),
        env: {
          ...process.env,
          SOC_DATABASE_URL: process.env.SOC_DATABASE_URL || "postgresql+psycopg://soc:soc@localhost:5434/soc",
          SOC_REDIS_URL: process.env.SOC_REDIS_URL || "redis://localhost:6379/0",
        },
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("close", (code) => resolve({ code: code ?? 1, stdout: stdout.trim(), stderr: stderr.trim() }));
    child.on("error", (error) => resolve({ code: 1, stdout: "", stderr: error.message }));
  });
}
