import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminReportsClient } from "./AdminReportsClient";

export const metadata: Metadata = {
  title: "Reports",
  description: "Platform-wide usage, revenue, and cache-savings summary.",
};

export default function AdminReportsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Reports" description="Usage, revenue, and cache-savings summary across all tenants." />
      <AdminReportsClient />
    </div>
  );
}
