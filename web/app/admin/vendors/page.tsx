import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { VendorsListClient } from "./VendorsListClient";

export const metadata: Metadata = {
  title: "Vendors",
  description: "All field-survey vendors on the platform — accuracy, SLA compliance, and verification status.",
};

export default function VendorsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Vendors" description="Every field-survey vendor on the platform." />
      <VendorsListClient />
    </div>
  );
}
