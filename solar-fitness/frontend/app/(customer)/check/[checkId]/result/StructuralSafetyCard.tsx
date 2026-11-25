import { Card } from "@/components/ui/Primitives";
import { SimpleStatus } from "@/components/ui/SimpleStatus";
import type { Assessment } from "@/lib/types";

// engine/fitness.py:147 — the structural gate (packs/rooftop.py::
// structural_gate()) is a real, deliberate, always-PENDING stub today:
// "structural assessment not yet implemented". That PENDING status
// reaches the customer as Condition(code="GATE_PENDING", detail="structural").
// This card is a presentational read of that real condition — it does
// NOT hardcode a check-needed banner, and renders nothing if the
// condition isn't present (e.g. an older assessment predating this
// condition, or if the gate somehow evaluates non-PENDING in future).
export function StructuralSafetyCard({ assessment }: { assessment: Assessment }) {
  const structuralPending = (assessment.conditions ?? []).find(
    (c) => c.code === "GATE_PENDING" && c.detail === "structural",
  );

  if (!structuralPending) return null;

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">🏗️</span>
        <p className="text-sm font-semibold text-ink">Roof strength</p>
      </div>
      <SimpleStatus
        tone="check"
        headline="An engineer needs to check your roof strength"
        description="This makes sure your roof can safely hold the solar panels and mounting structure."
      />
    </Card>
  );
}
