"use client";

import {
  Activity,
  Bell,
  Bot,
  Briefcase,
  ClipboardCheck,
  LayoutDashboard,
  LogOut,
  Network,
  Settings,
  Shield,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { Sentinel } from "@/components/sentinel/panel";
import { cn } from "@/lib/cn";
import { canAdminister, canReview } from "@/lib/operators";
import type { SessionClaims } from "@/lib/session-token";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, review: false, admin: false },
  { href: "/alerts", label: "Alerts", icon: Bell, review: false, admin: false },
  { href: "/cases", label: "Cases", icon: Briefcase, review: false, admin: false },
  { href: "/investigations", label: "Investigations", icon: Activity, review: false, admin: false },
  { href: "/entities", label: "Entities", icon: Network, review: false, admin: false },
  { href: "/agent-workspace", label: "Agent workspace", icon: Bot, review: false, admin: false },
  { href: "/reviews", label: "Review queue", icon: ClipboardCheck, review: true, admin: false },
  { href: "/admin", label: "Administration", icon: Settings, review: false, admin: true },
];

export function Shell({ session, children }: { session: SessionClaims; children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const items = NAV.filter((item) => {
    if (item.admin) return canAdminister(session.role);
    if (item.review) return canReview(session.role);
    return true;
  });

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <div className="grid min-h-screen grid-cols-[232px_1fr]">
      <aside className="sticky top-0 flex h-screen flex-col border-r border-border bg-[#070d18]/95 px-3 py-4">
        <div className="mb-6 flex items-center gap-2 px-2">
          <Shield className="h-5 w-5 text-accent" />
          <div>
            <p className="text-sm font-semibold tracking-tight">SOC Console</p>
            <p className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Operations</p>
          </div>
        </div>
        <nav className="space-y-1">
          {items.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground",
                  active && "bg-accent/10 text-foreground shadow-[inset_2px_0_0_hsl(var(--accent))]",
                )}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 px-2 pt-4">
          <div>
            <p className="text-sm">{session.name}</p>
            <p className="text-xs capitalize text-muted-foreground">{session.role}</p>
            <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{session.tenantId}</p>
          </div>
          <button className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground" onClick={signOut}>
            <LogOut className="h-3.5 w-3.5" />
            Sign out
          </button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-border bg-[#070d18]/80 px-6 backdrop-blur">
          <p className="text-sm text-muted-foreground">Task workspace · cited records · human approval</p>
          <p className="font-mono text-xs text-muted-foreground">{session.tenantId}</p>
        </header>
        <main className="px-6 py-5">{children}</main>
      </div>
      <Sentinel role={session.role} />
    </div>
  );
}
