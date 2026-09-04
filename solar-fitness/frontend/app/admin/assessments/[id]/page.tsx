import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AssessmentReviewClient } from "./AssessmentReviewClient";

export const metadata: Metadata = {
  title: "Review assessment",
  description: "Full feasibility checklist for admin review, approval, and vendor assignment.",
};

export default async function AdminAssessmentReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Feasibility review"
        description="Every check the resolver evaluated for this site. Approve to assign a vendor, or reject with a reason."
      />
      <AssessmentReviewClient assessmentId={id} />
    </div>
  );
}
