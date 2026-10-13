import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { Shell } from "@/components/shell";
import { QueryProvider } from "@/lib/query/provider";
import { openSession, SESSION_COOKIE } from "@/lib/session-token";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const session = await openSession(token);
  if (!session) redirect("/login");
  return (
    <QueryProvider>
      <Shell session={session}>{children}</Shell>
    </QueryProvider>
  );
}
