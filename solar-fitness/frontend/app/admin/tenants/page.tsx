import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { TenantsListClient } from "./TenantsListClient";

export const metadata: Metadata = {
  title: "Tenants",
  description: "All customer tenants on the platform — tier, status, seats, and usage.",
};

export default function TenantsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Tenants" description="Every customer organisation on the platform." />
      <TenantsListClient />
    </div>
  );
}
