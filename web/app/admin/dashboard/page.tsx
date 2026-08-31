import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminDashboardClient } from "./AdminDashboardClient";

export const metadata: Metadata = {
  title: "Admin dashboard",
  description: "Platform health, exceptions, and vendor activity across the whole platform.",
};

export default function AdminDashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Platform dashboard" description="Health, exceptions, and activity across the whole platform." />
      <AdminDashboardClient />
    </div>
  );
}
