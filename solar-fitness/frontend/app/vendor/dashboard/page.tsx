import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { VendorDashboardClient } from "./VendorDashboardClient";

export const metadata: Metadata = {
  title: "Vendor dashboard",
  description: "Today's job queue, SLA risk, and accuracy at a glance.",
};

export default function VendorDashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" description="Your job queue and accuracy at a glance." />
      <VendorDashboardClient />
    </div>
  );
}
