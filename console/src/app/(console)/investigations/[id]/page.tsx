import { InvestigationDetailView } from "@/components/views/investigation-detail";

export default async function InvestigationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InvestigationDetailView id={id} />;
}
