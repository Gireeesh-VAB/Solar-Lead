import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { InstallationsListClient } from "./InstallationsListClient";

export const metadata: Metadata = {
  title: "Installations",
  description: "Track installation projects and approve QC and commissioning.",
};

export default function AdminInstallationsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Installations"
        description="Every project opened by a customer accepting their quotation. Review the vendor's QC checklist and approve commissioning to complete a project."
      />
      <InstallationsListClient />
    </div>
  );
}
