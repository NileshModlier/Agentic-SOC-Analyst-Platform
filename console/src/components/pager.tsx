import { Button } from "@/components/ui/button";

export function Pager({
  page,
  onPrevious,
  onNext,
  hasPrevious,
  hasNext,
}: {
  page: number;
  hasPrevious: boolean;
  onPrevious: () => void;
  onNext: () => void;
  hasNext: boolean;
}) {
  return (
    <div className="mt-3 flex items-center justify-between text-sm text-muted-foreground">
      <span>Page {page}</span>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={!hasPrevious} onClick={onPrevious}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={!hasNext} onClick={onNext}>
          Next
        </Button>
      </div>
    </div>
  );
}
