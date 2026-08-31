import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { VerificationQueueClient } from "./VerificationQueueClient";

export const metadata: Metadata = {
  title: "Vendor verification queue",
  description: "Review and approve or reject vendors awaiting platform verification.",
};

export default function VendorVerificationPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Verification queue" description="New vendors awaiting onboarding review." />
      <VerificationQueueClient />
    </div>
  );
}
