import type { Assessment } from "@/lib/types";
import { Card } from "@/components/ui/Primitives";
import { CONSTRAINT_KIND_LABEL, formatDateTime, formatKwp } from "@/lib/utils";
import { cn } from "@/lib/utils";

// Everything one level down from the top-line verdict/capacity/confidence/
// binding-constraint block: full ceiling ledger, generation estimates,
// vision refinement, and provenance. The ML score panel is intentionally
// separate (see MLScorePanel) so it never competes visually with the verdict.
export function CeilingLedgerTable({ assessment }: { assessment: Assessment }) {
  if (assessment.ceilingLedger.length === 0) {
    return <p className="text-sm text-ink-soft">No ceiling ledger available — insufficient data to compute capacity ceilings.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th className="py-2 pr-3 font-medium">Ceiling</th>
            <th className="py-2 pr-3 font-medium">Kind</th>
            <th className="py-2 pr-3 font-medium text-right">Capacity</th>
          </tr>
        </thead>
        <tbody>
          {assessment.ceilingLedger.map((entry) => (
            <tr key={entry.label} className={cn("border-b border-line/60", entry.isBinding && "bg-[var(--warn-bg)]")}>
              <td className="py-2 pr-3 text-ink">
                {entry.label}
                {entry.isBinding && (
                  <span className="ml-2 rounded-[3px] px-1.5 py-0.5 text-[10px] font-semibold uppercase" style={{ background: "var(--warn)", color: "#fff" }}>
                    Binding
                  </span>
                )}
              </td>
              <td className="py-2 pr-3 text-ink-soft">{CONSTRAINT_KIND_LABEL[entry.kind]}</td>
              <td className="py-2 pr-3 text-right font-mono tabular text-ink">
                {/* A ceiling that could not be evaluated is not a ceiling
                    of zero — showing 0 kWp would claim the opposite of
                    what insufficient_data means. */}
                {entry.kwp == null ? <span className="text-ink-faint">—</span> : formatKwp(entry.kwp)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GenerationEstimateCard({ assessment }: { assessment: Assessment }) {
  if (!assessment.generation) {
    return (
      <Card className="p-4">
        <p className="text-sm text-ink-soft">No generation estimate available for this verdict.</p>
      </Card>
    );
  }
  return (
    <Card className="p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Annual generation estimate</p>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="font-mono tabular text-lg text-ink">{assessment.generation.p50AnnualKwh.toLocaleString("en-IN")} kWh</p>
          <p className="text-xs text-ink-soft">P50</p>
        </div>
        <div>
          <p className="font-mono tabular text-lg text-ink">{assessment.generation.p90AnnualKwh.toLocaleString("en-IN")} kWh</p>
          <p className="text-xs text-ink-soft">P90</p>
        </div>
      </div>
    </Card>
  );
}

export function VisionRefinementNote({ assessment }: { assessment: Assessment }) {
  if (!assessment.visionRefinement) return null;
  const { deltaKwp, note } = assessment.visionRefinement;
  return (
    <Card className="p-4">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">Vision (VIS) refinement</p>
      <p className="text-sm text-ink">
        Adjusted capacity by{" "}
        <span className="font-mono tabular" style={{ color: deltaKwp >= 0 ? "var(--good)" : "var(--bad)" }}>
          {deltaKwp >= 0 ? "+" : ""}
          {deltaKwp} kWp
        </span>
      </p>
      <p className="mt-1 text-sm text-ink-soft">{note}</p>
    </Card>
  );
}

export function ProvenanceFooter({ assessment }: { assessment: Assessment }) {
  return (
    <p className="font-mono tabular text-xs text-ink-faint">
      Assessment {assessment.id} · model {assessment.modelVersion} · assessed {formatDateTime(assessment.assessedAt)}
    </p>
  );
}
