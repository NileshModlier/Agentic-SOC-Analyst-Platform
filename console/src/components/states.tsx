import { Button } from "@/components/ui/button";

export function LoadingBlock({ label = "Loading records" }: { label?: string }) {
  return (
    <div className="panel rounded-lg p-4" role="status">
      <div className="mb-3 h-3 w-32 animate-pulse rounded bg-white/10" />
      <div className="space-y-2">
        <div className="h-8 animate-pulse rounded bg-white/5" />
        <div className="h-8 animate-pulse rounded bg-white/5" />
        <div className="h-8 animate-pulse rounded bg-white/5" />
      </div>
      <p className="sr-only">{label}</p>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel rounded-lg border-danger/40 p-4" role="alert">
      <p className="text-sm font-medium text-danger">The request failed</p>
      <p className="mt-1 text-sm text-muted-foreground">{message}</p>
      {onRetry ? (
        <Button className="mt-3" variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="panel rounded-lg p-6 text-center">
      <p className="text-sm font-medium">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{body}</p>
    </div>
  );
}
