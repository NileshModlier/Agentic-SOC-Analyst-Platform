"use client";

import { ChevronDown, Moon, Shield, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { guideFor, type GuideLink } from "@/components/sentinel/content";
import { cn } from "@/lib/cn";
import { canAdminister, canReview } from "@/lib/operators";
import type { Role } from "@/lib/session-token";

type Appearance = "system" | "dark" | "light";

type Persisted = {
  open: boolean;
  appearance: Appearance;
};

const STORAGE_KEY = "soc.sentinel";

export function Sentinel({ role }: { role: Role }) {
  const pathname = usePathname();
  const guide = guideFor(pathname);
  const panelId = useId();
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(true);
  const [appearance, setAppearance] = useState<Appearance>("system");
  const [resolved, setResolved] = useState<"dark" | "light">("dark");
  const [section, setSection] = useState(0);

  useEffect(() => {
    const stored = readPersisted();
    setOpen(stored.open);
    setAppearance(stored.appearance);
    setReady(true);
  }, []);

  useEffect(() => {
    setSection(0);
  }, [guide.id]);

  useEffect(() => {
    if (!ready) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ open, appearance } satisfies Persisted));
  }, [ready, open, appearance]);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const apply = () => {
      if (appearance === "light") setResolved("light");
      else if (appearance === "dark") setResolved("dark");
      else setResolved(media.matches ? "light" : "dark");
    };
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [appearance]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!ready) return null;

  const links = guide.links.filter((link) => canFollow(link, role));

  if (!open) {
    return (
      <button
        type="button"
        className="sentinel fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full border px-3 py-2 text-sm shadow-lg"
        data-appearance={resolved}
        aria-expanded="false"
        aria-controls={panelId}
        onClick={() => setOpen(true)}
      >
        <Shield className="h-4 w-4" aria-hidden />
        Sentinel
      </button>
    );
  }

  return (
    <section
      id={panelId}
      className="sentinel fixed bottom-5 right-5 z-40 flex w-[min(22rem,calc(100vw-2rem))] max-h-[min(34rem,calc(100vh-2.5rem))] flex-col overflow-hidden rounded-xl border shadow-2xl"
      data-appearance={resolved}
      aria-label="Sentinel, Security Operations Guide"
    >
      <header className="flex items-start gap-2 border-b px-3 py-3">
        <Shield className="mt-0.5 h-5 w-5 shrink-0 text-[var(--s-accent)]" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold leading-tight">Sentinel</p>
          <p className="text-[11px] uppercase tracking-[0.14em] text-[var(--s-muted)]">Security Operations Guide</p>
        </div>
        <button
          type="button"
          className="rounded-md p-1 text-[var(--s-muted)] hover:text-[var(--s-fg)]"
          aria-label={resolved === "light" ? "Use the dark guide" : "Use the light guide"}
          onClick={() => setAppearance(resolved === "light" ? "dark" : "light")}
        >
          {resolved === "light" ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
        </button>
        <button
          type="button"
          className="rounded-md p-1 text-[var(--s-muted)] hover:text-[var(--s-fg)]"
          aria-label="Collapse Sentinel"
          onClick={() => setOpen(false)}
        >
          <X className="h-4 w-4" />
        </button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--s-accent)]">{guide.title}</p>
        <p className="mt-1 text-sm leading-5">{guide.summary}</p>
        <div className="mt-3 space-y-1">
          {guide.sections.map((item, index) => {
            const expanded = section === index;
            return (
              <div key={item.title} className="rounded-md border border-[var(--s-border)]">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-2 px-2 py-2 text-left text-sm"
                  aria-expanded={expanded}
                  onClick={() => setSection(expanded ? -1 : index)}
                >
                  {item.title}
                  <ChevronDown className={cn("h-4 w-4 shrink-0 transition", expanded && "rotate-180")} />
                </button>
                {expanded ? <p className="px-2 pb-2 text-sm leading-5 text-[var(--s-muted)]">{item.body}</p> : null}
              </div>
            );
          })}
        </div>
        {links.length > 0 ? (
          <ul className="mt-3 space-y-1">
            {links.map((link) => (
              <li key={link.href}>
                <Link className="text-sm text-[var(--s-accent)] underline-offset-2 hover:underline" href={link.href}>
                  {link.label}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <footer className="border-t px-3 py-2 text-[11px] leading-4 text-[var(--s-muted)]">
        Sentinel explains this page. It does not investigate, decide, or call a model.
      </footer>
    </section>
  );
}

function canFollow(link: GuideLink, role: Role) {
  if (link.access === "review") return canReview(role);
  if (link.access === "admin") return canAdminister(role);
  return true;
}

function readPersisted(): Persisted {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return { open: true, appearance: "system" };
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    const appearance = parsed.appearance === "light" || parsed.appearance === "dark" || parsed.appearance === "system"
      ? parsed.appearance
      : "system";
    return { open: parsed.open !== false, appearance };
  } catch {
    return { open: true, appearance: "system" };
  }
}
