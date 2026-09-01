import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getAdminVendorServer as getAdminVendor } from "@/lib/api/serverFetch";
import { PageHeader } from "@/components/ui/Primitives";
import { VendorDetailClient } from "./VendorDetailClient";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const vendor = await getAdminVendor(id).catch(() => null);
  if (!vendor) return { title: "Vendor not found" };
  return {
    title: `${vendor.name} — vendor`,
    description: `Vendor detail for ${vendor.name}: performance, submissions, and payouts.`,
  };
}

export default async function VendorDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const vendor = await getAdminVendor(id).catch(() => null);
  if (!vendor) notFound();

  return (
    <div className="space-y-6">
      <PageHeader title={vendor.name} description={`Vendor ${vendor.id} · ${vendor.serviceArea}`} />
      <VendorDetailClient vendorId={vendor.id} />
    </div>
  );
}
