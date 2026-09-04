import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CalendarClock, Loader2, MapPin } from "lucide-react";
import { getCheckServer as getCheck } from "@/lib/api/serverFetch";
import { VERDICT_EXPLAINER } from "@/lib/fixtures/customer";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { BindingConstraintTag } from "@/components/ui/BindingConstraintTag";
import { Button, Card } from "@/components/ui/Primitives";
import { CalculationBreakdown } from "./CalculationBreakdown";
import { ResultMap } from "./ResultMap";
import { formatKwp } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Your result",
  robots: { index: false, follow: false },
};

const POSITIVE_VERDICTS = new Set(["SUITABLE", "SUITABLE_SUBJECT_TO_SURVEY", "CONDITIONAL"]);

export default async function ResultPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  const check = await getCheck(checkId).catch(() => null);
  if (!check) notFound();

  const assessment = check.latestAssessment;

  if (!assessment) {
    // Shouldn't normally be reached — the processing step attaches a result
    // before redirecting here — but handle it gracefully rather than 404.
    return (
      <div className="mx-auto flex max-w-sm flex-col items-center gap-4 py-16 text-center">
        <Loader2 size={28} strokeWidth={1.75} className="animate-spin text-amber" aria-hidden="true" />
        <p className="text-sm text-ink-soft">Still finishing up this check.</p>
        <Link href={`/check/${checkId}/processing`}>
          <Button variant="secondary">Go to processing</Button>
        </Link>
      </div>
    );
  }

  const isPositive = POSITIVE_VERDICTS.has(assessment.verdict);

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div className="text-center">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{check.name}</p>
        <div className="mt-2 flex justify-center">
          <VerdictChip verdict={assessment.verdict} size="lg" />
        </div>
      </div>

      <Card className="p-5 text-center">
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Estimated system size</p>
        <p className="mt-1 text-3xl font-semibold text-ink">
          {assessment.capacityKwp > 0 ? formatKwp(assessment.capacityKwp) : "—"}
        </p>
        <div className="mt-3 flex justify-center">
          <ConfidenceMeter tier={assessment.confidence} />
        </div>
      </Card>

      <Card className="p-4">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Why</p>
        <BindingConstraintTag constraint={assessment.bindingConstraint} />
      </Card>

      {/* CON-04. The tag above names the deciding constraint; this says
          what that actually means for this roof. Renders nothing when an
          older assessment carries no ledger. */}
      <CalculationBreakdown assessment={assessment} />

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Location</p>
        <ResultMap
          checkId={check.id}
          pin={{
            id: check.id,
            lat: check.location.lat,
            lng: check.location.lng,
            label: check.name,
            verdict: assessment.verdict,
          }}
          roofBoundary={check.boundary}
          boundaryIsApproximate={check.boundaryIsApproximate ?? true}
          canEditBoundary={(check.boundary?.length ?? 0) >= 3}
          height={300}
        />
        <p className="mt-1.5 flex items-center gap-1 text-xs text-ink-faint">
          <MapPin size={12} strokeWidth={1.75} aria-hidden="true" />
          {check.address}
        </p>
      </div>

      <Card className="p-4">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-ink-faint">What this means</p>
        <p className="text-sm text-ink">{VERDICT_EXPLAINER[assessment.verdict]}</p>
      </Card>

      {assessment.verdict === "SUITABLE_SUBJECT_TO_SURVEY" && (
        <div
          className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
          style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
        >
          <CalendarClock size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div>
            <p className="font-medium">Site survey requested</p>
            <p className="mt-0.5 text-xs opacity-90">
              We&apos;ve queued a verified installer to visit and confirm the roof in person. You&apos;ll be notified here once the survey is complete.
            </p>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Link href="/check/new" className="flex-1">
          <Button variant="secondary" className="w-full">
            Check another location
          </Button>
        </Link>
        {isPositive && (
          <Button className="flex-1" disabled title="Coming soon">
            Get connected
          </Button>
        )}
      </div>
    </div>
  );
}
