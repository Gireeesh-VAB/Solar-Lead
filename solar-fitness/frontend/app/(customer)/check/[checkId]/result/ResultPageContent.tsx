"use client";

import {
  AlertTriangle,
  CalendarClock,
  MapPin,
  Sun,
  Grid3x3,
  IndianRupee,
  Landmark,
  LineChart,
  Compass,
  ShieldCheck,
  Construction,
  ShieldAlert,
  ClipboardList,
  HardHat,
} from "lucide-react";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { BindingConstraintTag } from "@/components/ui/BindingConstraintTag";
import { Card } from "@/components/ui/Primitives";
import { ExpandableSection } from "@/components/ui/ExpandableSection";
import { AnimatedSection } from "./AnimatedSection";
import { CalculationBreakdown } from "./CalculationBreakdown";
import { SuitabilityScoreCard } from "./SuitabilityScoreCard";
import { ScoreBreakdownList } from "./ScoreBreakdownList";
import { ConfidenceBreakdownList } from "./ConfidenceBreakdownList";
import { RoofInfoCard } from "./RoofInfoCard";
import { SolarPotentialCard } from "./SolarPotentialCard";
import { FinancialCard } from "./FinancialCard";
import { SubsidyBreakdownCard } from "./SubsidyBreakdownCard";
import { FinancialAnalysisSection } from "./FinancialAnalysisSection";
import { ObstructionsList } from "./ObstructionsList";
import { PanelLayoutCard } from "./PanelLayoutCard";
import { RiskList } from "./RiskList";
import { StructuralSafetyCard } from "./StructuralSafetyCard";
import { ElectricalSafetyCard } from "./ElectricalSafetyCard";
import { FinalVerdictCard } from "./FinalVerdictCard";
import { InstallationSection } from "./InstallationSection";
import { ResultMap } from "./ResultMap";
import { Scene3DSection } from "@/components/panorama/Scene3DSection";
import { useCheckSolarLayout, useCheckObstacles, useCheckFinancialProjection } from "@/lib/query/hooks";
import { sunlightTier } from "@/lib/simpleLanguage";
import { VERDICT_EXPLAINER } from "@/lib/fixtures/customer";
import { formatKwp, formatInr } from "@/lib/utils";
import { parseRoofSegments } from "@/lib/types";
import type { Assessment, Site } from "@/lib/types";

/** Mirrors SolarPotentialCard's own private helper — same assessment field,
 *  same shape check — used only to decide whether the "Solar Potential"
 *  section has anything to show, never to compute a new value. */
function hasEmbeddedPanelLayout(panelLayout: Assessment["panelLayout"]): boolean {
  if (!panelLayout || typeof panelLayout !== "object") return false;
  return (panelLayout as Record<string, unknown>).status === "ok";
}

// Every informational card from the customer result page
// (app/(customer)/check/[checkId]/result/page.tsx), extracted so it can
// be shown a second place: embedded directly in the admin assessment
// review page (app/admin/assessments/[id]/AssessmentReviewClient.tsx),
// not just linked to. Reused as-is by the customer page too — one
// implementation, never two that can drift apart.
//
// Deliberately EXCLUDES three things the customer page also renders:
// the "Check another location"/"Raise enquiry" CTA row and its sticky
// mobile bar (customer navigation actions, meaningless to an admin
// reviewer), and UsnCaptureFlow (a customer-owned MUTATION form — its
// capture/confirm endpoints were deliberately kept customer-only when
// read access was widened for the admin embed, so showing it here
// would offer a submit button that just 404s).
//
// Below the always-visible hero (verdict, score, capacity), every other
// card is grouped into a premium ExpandableSection (components/ui/
// ExpandableSection.tsx) — a page-level accordion, collapsed by default
// for a customer so the page scans as a handful of named topics instead
// of a 3,000px wall of cards, but defaultSectionsOpen for the admin
// embed so a reviewer never has to click to see anything. Every card's
// own internals, data fetching, and null-guards are untouched — sections
// are only ever a new grouping/animation layer around the same
// components, gated by the same "is there anything to show" checks each
// card already makes internally.
export function ResultPageContent({
  assessment,
  check,
  defaultSectionsOpen = false,
}: {
  assessment: Assessment;
  check: Site;
  /** Admin embed passes true so reviewers see everything expanded; the
   *  customer result page leaves this false (collapsed-by-default). */
  defaultSectionsOpen?: boolean;
}) {
  // Presence checks below mirror each card's OWN internal null-guard —
  // duplicated only as booleans for section-level gating, never as a
  // second source of truth for a value. Sharing the same query hooks/keys
  // the leaf cards already call means React Query dedupes the request;
  // nothing here fires an extra network call.
  const solarLayout = useCheckSolarLayout(check.id);
  const obstacles = useCheckObstacles(check.id);
  const financialProjection = useCheckFinancialProjection(check.id);

  const shadingAvailable = !!check.shadingSource && check.shadingSource !== "unavailable";
  const sun = sunlightTier(shadingAvailable ? check.shadingScore : null);
  const roofSegments = parseRoofSegments(assessment.roofSegments);
  const hasRoofInfo = assessment.totalAreaM2 != null || assessment.usableAreaM2 != null || roofSegments.length > 0;
  const hasSolarPotential =
    !!assessment.generation || hasEmbeddedPanelLayout(assessment.panelLayout) || shadingAvailable;
  const showSolarPotentialSection = hasRoofInfo || hasSolarPotential;
  const solarPotentialSummary = [
    shadingAvailable && sun.label !== "Not available" ? `${sun.label} sunlight` : null,
    assessment.usableAreaM2 != null ? `${Math.round(assessment.usableAreaM2).toLocaleString()} m² usable roof` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const hasPanelLayoutData =
    !!solarLayout.data && solarLayout.data.status === "ok" && solarLayout.data.panels.length > 0;
  const panelLayoutSummary = hasPanelLayoutData
    ? `${solarLayout.data!.panelCount} panels · ${solarLayout.data!.totalKwp.toFixed(1)} kW`
    : undefined;

  const financials = assessment.financialEstimate;
  const savingsSummary = financials
    ? financials.annualSavingsInr != null
      ? `${formatInr(financials.annualSavingsInr)} estimated savings / year`
      : financials.totalProjectCostInr != null
        ? `Estimated cost: ${formatInr(financials.totalProjectCostInr)}`
        : undefined
    : undefined;

  const subsidySummary =
    financials?.subsidySchemeMaxAmountInr == null
      ? "Can't be determined yet"
      : !financials.subsidyApplicable
        ? "Not eligible"
        : financials.subsidyAmountInr != null
          ? `Save ${formatInr(financials.subsidyAmountInr)}`
          : "Eligible";

  const hasConfidenceBreakdown =
    !!assessment.confidenceComponents && Object.values(assessment.confidenceComponents).some((v) => v != null);

  const obstacleCount = obstacles.data?.obstacles.length ?? 0;
  const obstructionsSummary = obstacles.data
    ? obstacleCount === 0
      ? "Nothing detected"
      : `${obstacleCount} thing${obstacleCount === 1 ? "" : "s"} on your roof`
    : undefined;

  const isInstallationApproved = assessment.reviewStatus === "approved";

  const subsidyShort =
    financials?.subsidySchemeMaxAmountInr == null
      ? "—"
      : !financials.subsidyApplicable
        ? "Not eligible"
        : financials.subsidyAmountInr != null
          ? formatInr(financials.subsidyAmountInr)
          : "Eligible";

  // Customer view: the page is deliberately short — headline numbers, the
  // map, three topic sections, and ONE "Detailed report" section holding
  // every technical card. Admin embed (defaultSectionsOpen) keeps the full
  // flat list of sections, all expanded.
  if (!defaultSectionsOpen) {
    return (
      <div>
      {/* ---------- Hero: identity + score + headline size ---------- */}
      <AnimatedSection className="relative isolate overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface px-4 py-7 sm:px-6 sm:py-9">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute -top-24 left-1/2 h-56 w-[26rem] -translate-x-1/2 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--amber-soft), transparent 70%)", opacity: 0.22 }}
          />
        </div>

        <div className="text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{check.name}</p>
          <div className="mt-2 flex justify-center">
            <VerdictChip verdict={assessment.verdict} size="lg" />
          </div>
        </div>

        <div className="mt-5">
          <SuitabilityScoreCard
            score={assessment.score}
            confidenceScore={assessment.confidenceScore}
            verdict={assessment.verdict}
          />
        </div>

        <Card className="mt-4 p-5 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Estimated system size</p>
          <p className="mt-1 text-3xl font-semibold text-ink">
            {assessment.capacityKwp > 0 ? formatKwp(assessment.capacityKwp) : "—"}
          </p>
          <div className="mt-3 flex justify-center">
            <ConfidenceMeter tier={assessment.confidence} />
          </div>
        </Card>
        {!defaultSectionsOpen && (
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            {[
              { label: "Savings / year", value: financials?.annualSavingsInr != null ? formatInr(financials.annualSavingsInr) : "—" },
              { label: "Subsidy", value: subsidyShort },
              { label: "Sunlight", value: shadingAvailable ? sun.label : "—" },
            ].map((t) => (
              <Card key={t.label} className="px-2 py-3">
                <p className="text-sm font-semibold text-ink sm:text-base">{t.value}</p>
                <p className="mt-0.5 text-[11px] text-ink-faint">{t.label}</p>
              </Card>
            ))}
          </div>
        )}
      </AnimatedSection>


        <div className="mt-4 space-y-3">
      {assessment.boundaryWarning && (
        <AnimatedSection className="mt-0">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-xs">{assessment.boundaryWarning}</p>
          </div>
        </AnimatedSection>
      )}

      {!!check.competingBuildingsNearby && (
        <AnimatedSection className="mt-0">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-xs">
              We found {check.competingBuildingsNearby} other building
              {check.competingBuildingsNearby === 1 ? "" : "s"} close to the pin. If the roof outline below
              doesn&apos;t look like this building, the pin may need to be repositioned.
            </p>
          </div>
        </AnimatedSection>
      )}

        </div>

        <div className="mt-4">
      <AnimatedSection>
        <ExpandableSection
          icon={MapPin}
          title="Roof Map & 3D Model"
          summary={check.address}
          tone="teal"
          defaultOpen
        >
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
            usableAreaM2={assessment.usableAreaM2}
            restrictedZones={check.exclusions ?? []}
            roofSegments={roofSegments
              .filter((s) => s.polygon)
              .map((s) => ({
                segmentIndex: s.segmentIndex,
                polygon: s.polygon!,
                pitchDeg: s.pitchDeg,
                azimuthDeg: s.azimuthDeg,
                areaM2: s.areaM2,
                sunshineQuantiles: s.sunshineQuantiles,
              }))}
            height={300}
          />
          <p className="mt-1.5 flex items-center gap-1 text-xs text-ink-faint">
            <MapPin size={12} strokeWidth={1.75} aria-hidden="true" />
            {check.address}
          </p>
          {(check.imageryQuality || check.imageryDate) && (
            <p className="mt-0.5 text-xs text-ink-faint">
              Satellite imagery
              {check.imageryQuality ? `: ${check.imageryQuality.toLowerCase()} quality` : ""}
              {check.imageryDate
                ? `${check.imageryQuality ? "," : ":"} dated ${new Date(check.imageryDate).toLocaleDateString("en-IN", { year: "numeric", month: "short" })}`
                : ""}
            </p>
          )}

          <Scene3DSection checkId={check.id} />
        </ExpandableSection>
      </AnimatedSection>

        </div>

        <div className="mt-3 space-y-3">
          <AnimatedSection>
            <ExpandableSection icon={IndianRupee} title="Your Savings" summary={[savingsSummary, subsidySummary !== "Can't be determined yet" ? `Subsidy: ${subsidySummary}` : null].filter(Boolean).join(" · ") || undefined} tone="good">
              {!!financials && <FinancialCard financials={financials} />}
              <SubsidyBreakdownCard financials={financials} district={check.district} state={check.state} />
              {!!financialProjection.data && (
                <ExpandableSection icon={LineChart} title="Year-by-year projection" tone="good">
                  <FinancialAnalysisSection checkId={check.id} eligibleForEnquiry={false} />
                </ExpandableSection>
              )}
            </ExpandableSection>
          </AnimatedSection>

          {(showSolarPotentialSection || hasPanelLayoutData) && (
            <AnimatedSection>
              <ExpandableSection icon={Sun} title="Your Solar System" summary={[panelLayoutSummary, solarPotentialSummary].filter(Boolean).join(" · ") || undefined} tone="amber">
                {showSolarPotentialSection && <RoofInfoCard assessment={assessment} site={check} />}
                {showSolarPotentialSection && <SolarPotentialCard assessment={assessment} site={check} />}
                {hasPanelLayoutData && <PanelLayoutCard checkId={check.id} />}
              </ExpandableSection>
            </AnimatedSection>
          )}

          <AnimatedSection>
            <ExpandableSection icon={ClipboardList} title="Summary & Next Steps" summary={VERDICT_EXPLAINER[assessment.verdict]} tone="brand">
              <FinalVerdictCard assessment={assessment} site={check} />
            </ExpandableSection>
          </AnimatedSection>

          <AnimatedSection>
            <ExpandableSection icon={Compass} title="Detailed Report" summary="How we reached this — for those who want the numbers" tone="neutral">
              <ExpandableSection icon={Compass} title="Why This Recommendation" tone="brand">
                <Card className="p-4">
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Why</p>
                  <BindingConstraintTag constraint={assessment.bindingConstraint} />
                </Card>
                <CalculationBreakdown assessment={assessment} />
                <ScoreBreakdownList assessment={assessment} />
              </ExpandableSection>
              {hasConfidenceBreakdown && (
                <ExpandableSection icon={ShieldCheck} title="Confidence Score" summary={assessment.confidenceExplanation?.[0]} tone="blue">
                  <ConfidenceBreakdownList assessment={assessment} />
                </ExpandableSection>
              )}
              {!!obstacles.data && (
                <ExpandableSection icon={Construction} title="Roof Obstructions" summary={obstructionsSummary} tone="amber">
                  <ObstructionsList checkId={check.id} />
                </ExpandableSection>
              )}
              <ExpandableSection icon={ShieldAlert} title="Risks & Safety Checks" tone="neutral">
                <RiskList assessment={assessment} />
                <StructuralSafetyCard assessment={assessment} />
                <ElectricalSafetyCard electricalReadiness={check.electricalReadiness} />
              </ExpandableSection>
            </ExpandableSection>
          </AnimatedSection>

          {isInstallationApproved && (
          <AnimatedSection>
            <ExpandableSection
              icon={HardHat}
              title="Installation Details"
              summary="Track your installation"
              tone="teal"
              defaultOpen={defaultSectionsOpen}
            >
              <InstallationSection
                checkId={check.id}
                reviewStatus={assessment.reviewStatus}
                financialEstimate={assessment.financialEstimate}
              />
            </ExpandableSection>
          </AnimatedSection>
        )}
        </div>

      {assessment.verdict === "SUITABLE_SUBJECT_TO_SURVEY" && (
        <AnimatedSection className="mt-4">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <CalendarClock size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">
                {check.surveyJobStatus === "submitted" ? "Site survey completed" : "Site survey requested"}
              </p>
              <p className="mt-0.5 text-xs opacity-90">
                {check.surveyJobStatus === "submitted"
                  ? "A verified installer has visited and confirmed the roof in person."
                  : check.surveyJobStatus === "accepted" || check.surveyJobStatus === "in_progress"
                    ? "A verified installer has accepted this job and will visit soon to confirm the roof in person."
                    : "A verified installer is queued to visit and confirm the roof in person."}
              </p>
            </div>
          </div>
        </AnimatedSection>
      )}
      </div>
    );
  }

  return (
    <div>
      {/* ---------- Hero: identity + score + headline size ---------- */}
      <AnimatedSection className="relative isolate overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface px-4 py-7 sm:px-6 sm:py-9">
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute -top-24 left-1/2 h-56 w-[26rem] -translate-x-1/2 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--amber-soft), transparent 70%)", opacity: 0.22 }}
          />
        </div>

        <div className="text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">{check.name}</p>
          <div className="mt-2 flex justify-center">
            <VerdictChip verdict={assessment.verdict} size="lg" />
          </div>
        </div>

        <div className="mt-5">
          <SuitabilityScoreCard
            score={assessment.score}
            confidenceScore={assessment.confidenceScore}
            verdict={assessment.verdict}
          />
        </div>

        <Card className="mt-4 p-5 text-center">
          <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Estimated system size</p>
          <p className="mt-1 text-3xl font-semibold text-ink">
            {assessment.capacityKwp > 0 ? formatKwp(assessment.capacityKwp) : "—"}
          </p>
          <div className="mt-3 flex justify-center">
            <ConfidenceMeter tier={assessment.confidence} />
          </div>
        </Card>
      </AnimatedSection>

      <div aria-hidden="true" className="my-7 border-t border-line" />

      <div className="space-y-3">
        {showSolarPotentialSection && (
          <AnimatedSection>
            <ExpandableSection
              icon={Sun}
              title="Solar Potential"
              summary={solarPotentialSummary || undefined}
              tone="amber"
              defaultOpen={defaultSectionsOpen}
            >
              <RoofInfoCard assessment={assessment} site={check} />
              <SolarPotentialCard assessment={assessment} site={check} />
            </ExpandableSection>
          </AnimatedSection>
        )}

        {hasPanelLayoutData && (
          <AnimatedSection>
            <ExpandableSection
              icon={Grid3x3}
              title="Recommended Solar System"
              summary={panelLayoutSummary}
              tone="blue"
              defaultOpen={defaultSectionsOpen}
            >
              <PanelLayoutCard checkId={check.id} />
            </ExpandableSection>
          </AnimatedSection>
        )}

        {!!financials && (
          <AnimatedSection>
            <ExpandableSection
              icon={IndianRupee}
              title="Savings & ROI"
              summary={savingsSummary}
              tone="good"
              defaultOpen={defaultSectionsOpen}
            >
              <FinancialCard financials={financials} />
            </ExpandableSection>
          </AnimatedSection>
        )}

        <AnimatedSection>
          <ExpandableSection
            icon={Landmark}
            title="Government Subsidy"
            summary={subsidySummary}
            tone="teal"
            defaultOpen={defaultSectionsOpen}
          >
            <SubsidyBreakdownCard financials={financials} district={check.district} state={check.state} />
          </ExpandableSection>
        </AnimatedSection>

        {!!financialProjection.data && (
          <AnimatedSection>
            <ExpandableSection
              icon={LineChart}
              title="Financial Projection"
              summary="Seasonal, year-by-year & financing breakdown"
              tone="good"
              defaultOpen={defaultSectionsOpen}
            >
              <FinancialAnalysisSection checkId={check.id} eligibleForEnquiry={false} />
            </ExpandableSection>
          </AnimatedSection>
        )}
      </div>

      <div aria-hidden="true" className="my-7 border-t border-line" />

      <div className="space-y-3">
        <AnimatedSection>
          <ExpandableSection
            icon={Compass}
            title="Why This Recommendation"
            summary="What's setting your recommended system size"
            tone="brand"
            defaultOpen={defaultSectionsOpen}
          >
            <Card className="p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Why</p>
              <BindingConstraintTag constraint={assessment.bindingConstraint} />
            </Card>
            <CalculationBreakdown assessment={assessment} />
            <ScoreBreakdownList assessment={assessment} />
          </ExpandableSection>
        </AnimatedSection>

        {hasConfidenceBreakdown && (
          <AnimatedSection>
            <ExpandableSection
              icon={ShieldCheck}
              title="Confidence Score & Explanation"
              summary={assessment.confidenceExplanation?.[0]}
              tone="blue"
              defaultOpen={defaultSectionsOpen}
            >
              <ConfidenceBreakdownList assessment={assessment} />
            </ExpandableSection>
          </AnimatedSection>
        )}

        {!!obstacles.data && (
          <AnimatedSection>
            <ExpandableSection
              icon={Construction}
              title="Roof Obstructions"
              summary={obstructionsSummary}
              tone="amber"
              defaultOpen={defaultSectionsOpen}
            >
              <ObstructionsList checkId={check.id} />
            </ExpandableSection>
          </AnimatedSection>
        )}
      </div>

      {assessment.boundaryWarning && (
        <AnimatedSection className="mt-4">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-xs">{assessment.boundaryWarning}</p>
          </div>
        </AnimatedSection>
      )}

      {!!check.competingBuildingsNearby && (
        <AnimatedSection className="mt-4">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <AlertTriangle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <p className="text-xs">
              We found {check.competingBuildingsNearby} other building
              {check.competingBuildingsNearby === 1 ? "" : "s"} close to the pin. If the roof outline below
              doesn&apos;t look like this building, the pin may need to be repositioned.
            </p>
          </div>
        </AnimatedSection>
      )}

      <div aria-hidden="true" className="my-7 border-t border-line" />

      <AnimatedSection>
        <ExpandableSection
          icon={MapPin}
          title="Roof Map & 3D Model"
          summary={check.address}
          tone="teal"
          defaultOpen
        >
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
            usableAreaM2={assessment.usableAreaM2}
            restrictedZones={check.exclusions ?? []}
            roofSegments={roofSegments
              .filter((s) => s.polygon)
              .map((s) => ({
                segmentIndex: s.segmentIndex,
                polygon: s.polygon!,
                pitchDeg: s.pitchDeg,
                azimuthDeg: s.azimuthDeg,
                areaM2: s.areaM2,
                sunshineQuantiles: s.sunshineQuantiles,
              }))}
            height={300}
          />
          <p className="mt-1.5 flex items-center gap-1 text-xs text-ink-faint">
            <MapPin size={12} strokeWidth={1.75} aria-hidden="true" />
            {check.address}
          </p>
          {(check.imageryQuality || check.imageryDate) && (
            <p className="mt-0.5 text-xs text-ink-faint">
              Satellite imagery
              {check.imageryQuality ? `: ${check.imageryQuality.toLowerCase()} quality` : ""}
              {check.imageryDate
                ? `${check.imageryQuality ? "," : ":"} dated ${new Date(check.imageryDate).toLocaleDateString("en-IN", { year: "numeric", month: "short" })}`
                : ""}
            </p>
          )}

          <Scene3DSection checkId={check.id} />
        </ExpandableSection>
      </AnimatedSection>

      <div className="mt-3 space-y-3">
        <AnimatedSection>
          <ExpandableSection
            icon={ShieldAlert}
            title="Eligibility & Safety Checks"
            summary="Risks, structural & electrical readiness"
            tone="neutral"
            defaultOpen={defaultSectionsOpen}
          >
            <RiskList assessment={assessment} />
            <StructuralSafetyCard assessment={assessment} />
            <ElectricalSafetyCard electricalReadiness={check.electricalReadiness} />
          </ExpandableSection>
        </AnimatedSection>

        <AnimatedSection>
          <ExpandableSection
            icon={ClipboardList}
            title="Assessment Summary"
            summary={VERDICT_EXPLAINER[assessment.verdict]}
            tone="brand"
            defaultOpen={defaultSectionsOpen}
          >
            <FinalVerdictCard assessment={assessment} site={check} />
          </ExpandableSection>
        </AnimatedSection>

        {isInstallationApproved && (
          <AnimatedSection>
            <ExpandableSection
              icon={HardHat}
              title="Installation Details"
              summary="Track your installation"
              tone="teal"
              defaultOpen={defaultSectionsOpen}
            >
              <InstallationSection
                checkId={check.id}
                reviewStatus={assessment.reviewStatus}
                financialEstimate={assessment.financialEstimate}
              />
            </ExpandableSection>
          </AnimatedSection>
        )}
      </div>

      {assessment.verdict === "SUITABLE_SUBJECT_TO_SURVEY" && (
        <AnimatedSection className="mt-4">
          <div
            className="flex items-start gap-2.5 rounded-[var(--radius-app)] border px-4 py-3 text-sm"
            style={{ borderColor: "var(--warn)", background: "var(--warn-bg)", color: "var(--warn)" }}
          >
            <CalendarClock size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <div>
              <p className="font-medium">
                {check.surveyJobStatus === "submitted" ? "Site survey completed" : "Site survey requested"}
              </p>
              <p className="mt-0.5 text-xs opacity-90">
                {check.surveyJobStatus === "submitted"
                  ? "A verified installer has visited and confirmed the roof in person."
                  : check.surveyJobStatus === "accepted" || check.surveyJobStatus === "in_progress"
                    ? "A verified installer has accepted this job and will visit soon to confirm the roof in person."
                    : "A verified installer is queued to visit and confirm the roof in person."}
              </p>
            </div>
          </div>
        </AnimatedSection>
      )}
    </div>
  );
}
