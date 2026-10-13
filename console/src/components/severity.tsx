import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { label } from "@/lib/format";

const TONE: Record<string, string> = {
  critical: "border-danger/40 bg-danger/15 text-danger",
  high: "border-orange-400/40 bg-orange-400/15 text-orange-300",
  medium: "border-warning/40 bg-warning/15 text-warning",
  low: "border-teal-300/40 bg-teal-300/10 text-teal-200",
  informational: "border-sky-300/40 bg-sky-300/10 text-sky-200",
  unknown: "border-border bg-white/5 text-muted-foreground",
  new: "border-accent/40 bg-accent/10 text-accent",
  open: "border-accent/40 bg-accent/10 text-accent",
  active: "border-accent/40 bg-accent/10 text-accent",
  pending_approval: "border-warning/40 bg-warning/10 text-warning",
  approved: "border-ok/40 bg-ok/15 text-ok",
  rejected: "border-danger/40 bg-danger/15 text-danger",
  validation_failed: "border-danger/40 bg-danger/15 text-danger",
  insufficient_evidence: "border-warning/40 bg-warning/10 text-warning",
  failed: "border-danger/40 bg-danger/15 text-danger",
  completed: "border-ok/40 bg-ok/15 text-ok",
  closed: "border-border bg-white/5 text-muted-foreground",
};

export function StatusBadge({ value, className }: { value: string | null | undefined; className?: string }) {
  const key = value || "unknown";
  return <Badge className={cn("normal-case tracking-normal", TONE[key], className)}>{label(key)}</Badge>;
}

export const SEVERITY_COLOR: Record<string, string> = {
  unknown: "#64748b",
  informational: "#7dd3fc",
  low: "#5eead4",
  medium: "#f5b942",
  high: "#fb923c",
  critical: "#fb7185",
};
