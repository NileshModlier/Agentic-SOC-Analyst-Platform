export function PageHeader({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="mb-5">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{detail}</p>
    </div>
  );
}
