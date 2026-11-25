"use client";

import { Card } from "@/components/ui/Primitives";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { VERDICT_EXPLAINER } from "@/lib/fixtures/customer";
import { sunlightTier } from "@/lib/simpleLanguage";
import { useT } from "@/lib/i18n/LanguageContext";
import type { Assessment, Site, Verdict } from "@/lib/types";
import { formatInr, formatKwp } from "@/lib/utils";

const VERDICT_ACCENT: Record<Verdict, string> = {
  SUITABLE: "var(--good)",
  SUITABLE_SUBJECT_TO_SURVEY: "var(--warn)",
  CONDITIONAL: "var(--warn)",
  INSUFFICIENT_DATA: "var(--neutral-verdict)",
  NOT_SUITABLE: "var(--bad)",
};

function panelCount(panelLayout: Assessment["panelLayout"]): number | null {
  if (!panelLayout || typeof panelLayout !== "object") return null;
  const status = (panelLayout as Record<string, unknown>).status;
  if (status !== "ok") return null;
  const count = (panelLayout as Record<string, unknown>).panelCount;
  return typeof count === "number" ? count : null;
}

/** A mini-stat recap tile — icon + label + value, or nothing when the
 *  underlying figure isn't available (never a fabricated placeholder). */
function RecapStat({ icon, label, value }: { icon: string; label: string; value: string | null }) {
  if (value == null) return null;
  return (
    <div className="rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] px-3 py-2.5">
      <p className="flex items-center gap-1 text-[11px] text-ink-faint">
        <span aria-hidden="true">{icon}</span>
        {label}
      </p>
      <p className="mt-0.5 text-sm font-semibold tabular text-ink">{value}</p>
    </div>
  );
}

// Consolidates the old "What this means" card + the standalone
// limitations paragraph into one closing section — verdict, why, and a
// recap grid of every key figure computed on this page (roof space,
// sunlight, panels, system size, generation, savings, payback), so the
// customer's last screen answers "what's my solar result" in one glance
// without needing to scroll back up. Every value here is read from data
// already computed by an earlier card on this page — nothing new is
// calculated.
const VERDICT_EXPLAINER_KEY: Record<Verdict, string> = {
  SUITABLE: "result.verdictExplainerSuitable",
  SUITABLE_SUBJECT_TO_SURVEY: "result.verdictExplainerSuitableSubjectToSurvey",
  CONDITIONAL: "result.verdictExplainerConditional",
  INSUFFICIENT_DATA: "result.verdictExplainerInsufficientData",
  NOT_SUITABLE: "result.verdictExplainerNotSuitable",
};

export function FinalVerdictCard({
  assessment,
  site,
}: {
  assessment: Assessment;
  site: Pick<Site, "shadingScore" | "shadingSource">;
}) {
  const { t } = useT();
  const accent = VERDICT_ACCENT[assessment.verdict];
  const hasCapacity = assessment.capacityKwp > 0;
  const sunshineAvailable = site.shadingSource && site.shadingSource !== "unavailable";
  const sun = sunlightTier(sunshineAvailable ? site.shadingScore : null);
  const financials = assessment.financialEstimate;

  return (
    <Card className="relative overflow-hidden p-4">
      <div aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ background: accent }} />
      <div className="mb-2 flex items-center gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
          {t("result.finalVerdictTitle", "Your solar result")}
        </p>
        <VerdictChip verdict={assessment.verdict} size="sm" />
      </div>
      <p className="text-sm text-ink">
        {t(VERDICT_EXPLAINER_KEY[assessment.verdict], VERDICT_EXPLAINER[assessment.verdict])}
      </p>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        <RecapStat
          icon="🏠"
          label="Roof space"
          value={assessment.usableAreaM2 != null ? `${Math.round(assessment.usableAreaM2).toLocaleString()} m²` : null}
        />
        <RecapStat icon="☀️" label="Sunlight" value={sun.label !== "Not available" ? sun.label : null} />
        <RecapStat icon="🔲" label="Panels" value={panelCount(assessment.panelLayout)?.toLocaleString() ?? null} />
        <RecapStat icon="⚡" label="System size" value={hasCapacity ? formatKwp(assessment.capacityKwp) : null} />
        <RecapStat
          icon="🔋"
          label="Annual power"
          value={
            assessment.generation?.estimatedKwhPerYear != null
              ? `${Math.round(assessment.generation.estimatedKwhPerYear).toLocaleString()} kWh`
              : null
          }
        />
        <RecapStat
          icon="💰"
          label="Annual savings"
          value={financials?.annualSavingsInr != null ? formatInr(financials.annualSavingsInr) : null}
        />
        <RecapStat
          icon="⏱️"
          label="Payback"
          value={financials?.paybackPeriodYears != null ? `${financials.paybackPeriodYears.toFixed(1)} yrs` : null}
        />
      </div>

      {assessment.limitations && (
        <p className="mt-3 text-[11px] leading-relaxed text-ink-faint">{assessment.limitations}</p>
      )}
    </Card>
  );
}
