"use client";

import Link from "next/link";
import { CalendarClock, Loader2, MapPin } from "lucide-react";
import { useCheck } from "@/lib/query/hooks";
import { VERDICT_EXPLAINER } from "@/lib/fixtures/customer";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { BindingConstraintTag } from "@/components/ui/BindingConstraintTag";
import { Button, Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { MapView } from "@/components/map/MapView";
import { formatKwp } from "@/lib/utils";

const POSITIVE_VERDICTS = new Set(["SUITABLE", "SUITABLE_SUBJECT_TO_SURVEY", "CONDITIONAL"]);

export function ResultClient({ checkId }: { checkId: string }) {
  const check = useCheck(checkId);

  if (check.isLoading) {
    return (
      <div className="mx-auto max-w-xl space-y-6">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }

  if (check.isError || !check.data) {
    return <ErrorState description="Could not load this check." onRetry={() => check.refetch()} />;
  }

  const site = check.data;
  const assessment = site.latestAssessment;

  if (!assessment) {
    // Shouldn't normally be reached — the processing step attaches a result
    // before redirecting here — but handle it gracefully rather than crash.
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
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{site.name}</p>
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

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Location</p>
        <MapView
          pins={[{ id: site.id, lat: site.location.lat, lng: site.location.lng, label: site.name, verdict: assessment.verdict }]}
          height={260}
        />
        <p className="mt-1.5 flex items-center gap-1 text-xs text-ink-faint">
          <MapPin size={12} strokeWidth={1.75} aria-hidden="true" />
          {site.address}
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
