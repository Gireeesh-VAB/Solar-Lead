import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AssessmentsListClient } from "./AssessmentsListClient";

export const metadata: Metadata = {
  title: "Assessments",
  description: "All site fitness assessments across the platform.",
};

export default function AdminAssessmentsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Assessments" description="Every fitness assessment run on the platform." />
      <AssessmentsListClient />
    </div>
  );
}
