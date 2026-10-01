import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { getCheckServer as getCheck, orRedirectToLogin } from "@/lib/api/serverFetch";
import { EnquiryClient } from "./EnquiryClient";

export const metadata: Metadata = {
  title: "Raise an enquiry",
  robots: { index: false, follow: false },
};

// The enquiry step, entered only from the result page's "Raise enquiry"
// button — deliberately its own route rather than inline on the result
// page, since raising an enquiry is a distinct customer decision, not a
// side effect of viewing a result (repositories/assessments.py::
// save_assessment()'s "not_submitted" default).
export default async function EnquiryPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  const check = await orRedirectToLogin(getCheck(checkId));
  if (!check) notFound();

  const assessment = check.latestAssessment;
  if (!assessment) redirect(`/check/${checkId}/processing`);

  const reviewStatus = assessment.reviewStatus;
  // Nothing eligible to raise an enquiry on, or one was already raised —
  // either way this page has nothing left to do. Idempotent on the
  // backend too, but there's no reason to show vendor-selection UI for
  // a decision that's already been made.
  if (!reviewStatus || reviewStatus === "not_applicable" || reviewStatus !== "not_submitted") {
    redirect(`/check/${checkId}/result`);
  }

  return (
    <EnquiryClient
      checkId={checkId}
      checkName={check.name}
      verdict={assessment.verdict}
      capacityKwp={assessment.capacityKwp}
    />
  );
}
