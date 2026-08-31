import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { JobsListClient } from "./JobsListClient";

export const metadata: Metadata = {
  title: "Job queue",
  description: "Browse and filter jobs assigned to you, sorted by deadline, distance, or payout.",
};

export default function VendorJobsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Job queue" description="Jobs assigned to you. Filter by status or sort by distance, deadline, or payout." />
      <JobsListClient />
    </div>
  );
}
