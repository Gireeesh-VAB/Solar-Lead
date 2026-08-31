import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTenant } from "@/lib/api/client";
import { PageHeader } from "@/components/ui/Primitives";
import { TenantDetailClient } from "./TenantDetailClient";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const tenant = await getTenant(id).catch(() => null);
  if (!tenant) return { title: "Tenant not found" };
  return {
    title: `${tenant.name} — tenant`,
    description: `Tenant detail for ${tenant.name}: tier, billing, seats, and usage.`,
  };
}

export default async function TenantDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const tenant = await getTenant(id).catch(() => null);
  if (!tenant) notFound();

  return (
    <div className="space-y-6">
      <PageHeader title={tenant.name} description={`Tenant ${tenant.id} · created ${new Date(tenant.createdAt).toLocaleDateString("en-IN")}`} />
      <TenantDetailClient tenantId={tenant.id} />
    </div>
  );
}
