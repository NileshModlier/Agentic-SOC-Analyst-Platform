export function formatTime(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return `${new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hourCycle: "h23",
  }).format(date)} UTC`;
}

export function dayKey(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown";
  return date.toISOString().slice(0, 10);
}

export function shortId(value: string | null | undefined) {
  if (!value) return "—";
  return value.slice(0, 8);
}

export function label(value: string | null | undefined) {
  if (!value) return "—";
  return value.replaceAll("_", " ");
}

export function countLabel(count: number, hasMore: boolean) {
  return hasMore ? `${count}+` : String(count);
}
