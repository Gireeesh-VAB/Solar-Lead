import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { NewVendorClient } from "./NewVendorClient";

export const metadata: Metadata = {
  title: "Add vendor",
  description: "Onboard a new field-survey vendor with a linked login account.",
};

export default function NewVendorPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Add vendor" description="Create a vendor profile and a linked login account." />
      <NewVendorClient />
    </div>
  );
}
