import { EntityDetailView } from "@/components/views/entity-detail";

export default async function EntityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <EntityDetailView id={id} />;
}
