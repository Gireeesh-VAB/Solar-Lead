import type { Assessment } from "@/lib/types";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { BindingConstraintTag } from "@/components/ui/BindingConstraintTag";
import { CacheProvenanceBadge } from "@/components/ui/CacheProvenanceBadge";
import { formatKwp } from "@/lib/utils";

// The core reusable "top of hierarchy" block: verdict, capacity, confidence,
// binding constraint — in that priority order, and nothing else competing
// for visual weight. Used on the site detail page, map popups, and cards.
export function AssessmentSummary({ assessment, compact = false }: { assessment: Assessment; compact?: boolean }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <VerdictChip verdict={assessment.verdict} size={compact ? "md" : "lg"} />
        <CacheProvenanceBadge cache={assessment.cache} />
      </div>
      <div>
        <p className="font-mono tabular text-3xl font-semibold text-ink">
          {assessment.capacityKwp > 0 ? formatKwp(assessment.capacityKwp) : "—"}
          <span className="ml-2 text-sm font-normal text-ink-soft">DC capacity</span>
        </p>
      </div>
      <ConfidenceMeter tier={assessment.confidence} />
      <div className="border-t border-line pt-3">
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">Binding constraint</p>
        <BindingConstraintTag constraint={assessment.bindingConstraint} />
      </div>
    </div>
  );
}
