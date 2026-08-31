import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminJurisdictionsClient } from "./AdminJurisdictionsClient";

export const metadata: Metadata = {
  title: "Jurisdiction packs",
  description: "Manage regulatory constraint packs by jurisdiction and publish new versions.",
};

export default function AdminJurisdictionsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Jurisdiction packs" description="Regulatory constraint packs applied by the fitness engine, by jurisdiction." />
      <AdminJurisdictionsClient />
    </div>
  );
}
