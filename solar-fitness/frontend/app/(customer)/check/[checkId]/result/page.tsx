import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Loader2 } from "lucide-react";
import { getCheckServer as getCheck, orRedirectToLogin } from "@/lib/api/serverFetch";
import { Button } from "@/components/ui/Primitives";
import { AnimatedSection } from "./AnimatedSection";
import { ResultPageContent } from "./ResultPageContent";
import { UsnCaptureFlow } from "@/components/sites/UsnCaptureFlow";

// domain/site.py's BILLING_LINKED_SITE_TYPES — USN capture only applies to
// these; other site types don't have a billing account to attach one to.
const BILLING_LINKED_SITE_TYPES = new Set(["ROOFTOP_RESIDENTIAL", "ROOFTOP_CI"]);

export const metadata: Metadata = {
  title: "Your result",
  robots: { index: false, follow: false },
};

const POSITIVE_VERDICTS = new Set(["SUITABLE", "SUITABLE_SUBJECT_TO_SURVEY", "CONDITIONAL"]);

export default async function ResultPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  const check = await orRedirectToLogin(getCheck(checkId));
  if (!check) notFound();

  const assessment = check.latestAssessment;

  if (!assessment) {
    // Shouldn't normally be reached — the processing step attaches a result
    // before redirecting here — but handle it gracefully rather than 404.
    return (
      <div className="mx-auto flex max-w-sm flex-col items-center gap-4 py-16 text-center">
        <Loader2 size={28} strokeWidth={1.75} className="animate-spin text-brand" aria-hidden="true" />
        <p className="text-sm text-ink-soft">Still finishing up this check.</p>
        <Link href={`/check/${checkId}/processing`}>
          <Button variant="secondary">Go to processing</Button>
        </Link>
      </div>
    );
  }

  const isPositive = POSITIVE_VERDICTS.has(assessment.verdict);

  // The primary actions live twice: once inline (desktop, where the page
  // is easily scrolled back to) and once in the sticky mobile bar below —
  // same components, same logic, just two placements so the long-scroll
  // result page always keeps them reachable on a phone.
  const ctaRow = (
    <>
      <Link href="/check/new" className="flex-1">
        <Button variant="secondary" className="w-full">
          Check another location
        </Button>
      </Link>
      {isPositive && <EnquiryCta checkId={check.id} reviewStatus={assessment.reviewStatus} />}
    </>
  );

  return (
    <div className="mx-auto max-w-xl pb-20 sm:pb-0">
      <ResultPageContent assessment={assessment} check={check} />

      {/* USN capture happens here, after the AI analysis has a result to
          attach it to — not on the intake form, where it would be one more
          thing standing between a customer and their first result. Only
          shown for billing-linked site types (USN-05); every customer
          check defaults to ROOFTOP_RESIDENTIAL, which qualifies. Kept out
          of ResultPageContent since it's a customer-owned mutation form,
          not something the admin embed should offer (see that file's own
          docstring). */}
      {BILLING_LINKED_SITE_TYPES.has(check.siteType) && (
        <AnimatedSection className="mt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
            Electricity connection number (USN)
          </p>
          <UsnCaptureFlow site={check} mobile />
        </AnimatedSection>
      )}

      {/* Inline CTA row — the primary reachable copy on desktop, where
          scrolling back down is trivial. Hidden on mobile in favour of the
          sticky bar below so the actions aren't offered twice on a phone. */}
      <div className="mt-6 hidden gap-2 sm:flex">{ctaRow}</div>

      {/* Sticky mobile action bar — this is the longest page in the app,
          so "Check another location" / "Raise enquiry" stay reachable
          without scrolling back up. Desktop keeps the inline row above
          instead, where a sticky bar would just be clutter. Positioned
          above the app's own mobile tab bar (app/(customer)/layout.tsx,
          "fixed ... bottom-0 ... md:hidden") rather than at bottom-0,
          so the two don't stack on top of each other. */}
      <div
        className="fixed inset-x-0 z-30 border-t border-line bg-surface/95 px-4 py-3 backdrop-blur-sm sm:hidden"
        style={{ bottom: "calc(60px + env(safe-area-inset-bottom))", boxShadow: "var(--shadow-float)" }}
      >
        <div className="mx-auto flex max-w-xl gap-2">{ctaRow}</div>
      </div>
    </div>
  );
}

// The enquiry and the feasibility check are deliberately separate stages
// (repositories/assessments.py::save_assessment()'s "not_submitted"
// default) — this button is the one entry point between them. Once an
// enquiry has been raised, re-entering the vendor-selection flow makes
// no sense, so a status affordance replaces it instead.
function EnquiryCta({ checkId, reviewStatus }: { checkId: string; reviewStatus?: string }) {
  if (!reviewStatus || reviewStatus === "not_submitted") {
    return (
      <Link href={`/check/${checkId}/enquiry`} className="flex-1">
        <Button className="w-full">Raise enquiry</Button>
      </Link>
    );
  }
  const label =
    reviewStatus === "pending"
      ? "Enquiry submitted — pending review"
      : reviewStatus === "approved"
        ? "Enquiry approved — vendor assigned"
        : reviewStatus === "rejected"
          ? "Enquiry not approved"
          : "Enquiry submitted";
  return (
    <Button className="flex-1" variant="secondary" disabled title={label}>
      {label}
    </Button>
  );
}
