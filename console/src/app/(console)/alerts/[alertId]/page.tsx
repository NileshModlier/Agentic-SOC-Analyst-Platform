import { AlertDetailView } from "@/components/views/alert-detail";

export default async function AlertPage({ params }: { params: Promise<{ alertId: string }> }) {
  const { alertId } = await params;
  return <AlertDetailView alertId={alertId} />;
}
