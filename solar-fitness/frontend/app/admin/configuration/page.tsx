import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminConfigurationClient } from "./AdminConfigurationClient";

export const metadata: Metadata = {
  title: "Configuration",
  description: "Feature flags, quotas, API keys, and third-party API status for the platform.",
};

export default function AdminConfigurationPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Configuration" description="Feature flags, quotas, and third-party API status." />
      <AdminConfigurationClient />
    </div>
  );
}
