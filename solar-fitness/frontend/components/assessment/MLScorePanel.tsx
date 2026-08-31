import { Info } from "lucide-react";
import type { Assessment } from "@/lib/types";
import { Card } from "@/components/ui/Primitives";

// Deliberately isolated in its own card, visually subordinate to the FIT
// verdict, with an explicit "supplementary, not authoritative" note. Never
// give this the same size/position/weight as VerdictChip + capacity.
export function MLScorePanel({ assessment }: { assessment: Assessment }) {
  if (assessment.mlSuitabilityScore == null) {
    return (
      <Card className="p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Model comparison</p>
        <p className="mt-2 text-sm text-ink-soft">No ML suitability score available for this assessment.</p>
      </Card>
    );
  }
  const pct = Math.round(assessment.mlSuitabilityScore * 100);
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Model comparison</p>
      <div className="mt-2 flex items-center gap-3">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: "var(--blue-soft)" }} />
        </div>
        <span className="font-mono tabular text-sm text-ink-soft">{pct}%</span>
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-faint">
        <Info size={13} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
        ML suitability score is a supplementary signal for model comparison and QA — it is never the authoritative
        fitness verdict. The verdict above is the decision of record.
      </p>
    </Card>
  );
}
