import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { InstallationsListClient } from "./InstallationsListClient";

export const metadata: Metadata = {
  title: "Installations",
  description: "Installation projects assigned to you after a customer accepted their quotation.",
};

export default function VendorInstallationsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Installations"
        description="Projects that opened when the customer accepted their quotation. Advance the stage as work completes, capture QC and geotagged photos, then submit commissioning."
      />
      <InstallationsListClient />
    </div>
  );
}
