import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { canAdminister, canReview } from "@/lib/operators";
import { openSession, SESSION_COOKIE } from "@/lib/session-token";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname.startsWith("/api/auth/login")) return NextResponse.next();
  const session = await openSession(request.cookies.get(SESSION_COOKIE)?.value);
  if (pathname === "/login") {
    if (session) return NextResponse.redirect(new URL("/dashboard", request.url));
    return NextResponse.next();
  }
  if (!session) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: { code: "unauthenticated", message: "Sign in required." } },
        { status: 401 },
      );
    }
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (pathname.startsWith("/reviews") && !canReview(session.role)) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  if ((pathname.startsWith("/admin") || pathname.startsWith("/api/operations")) && !canAdminister(session.role)) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { error: { code: "forbidden", message: "Administration is limited to the administrator role." } },
        { status: 403 },
      );
    }
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
