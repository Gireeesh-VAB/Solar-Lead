import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { SubmissionsListClient } from "./SubmissionsListClient";

export const metadata: Metadata = {
  title: "Submissions",
  description: "Jobs you've submitted for reconciliation, with payout and dispute status.",
};

export default function VendorSubmissionsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Submissions" description="History of jobs you've submitted, and their reconciliation status." />
      <SubmissionsListClient />
    </div>
  );
}
