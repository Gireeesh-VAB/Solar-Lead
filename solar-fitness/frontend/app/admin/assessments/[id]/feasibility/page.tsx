import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AssessmentFeasibilityClient } from "../AssessmentFeasibilityClient";

export const metadata: Metadata = {
  title: "Feasibility details",
  description: "Full customer result view, checklist, system sizing, and grid/financial feasibility for this assessment.",
};

export default async function AdminAssessmentFeasibilityPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Feasibility details"
        description="The full result the customer sees, plus the checklist and grid/financial feasibility forms."
      />
      <AssessmentFeasibilityClient assessmentId={id} />
    </div>
  );
}
