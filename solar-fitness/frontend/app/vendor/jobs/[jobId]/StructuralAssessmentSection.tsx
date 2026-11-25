"use client";

import { useState } from "react";
import { Card, Button, Badge } from "@/components/ui/Primitives";
import { useSaveStructuralAssessment } from "@/lib/query/hooks";
import type { StructuralAssessment, StructuralCondition, VendorJob } from "@/lib/types";

const CONDITION_LABEL: Record<StructuralCondition, string> = {
  NEW: "New",
  GOOD: "Good",
  AVERAGE: "Average",
  POOR: "Poor",
  DAMAGED: "Damaged",
  UNDER_CONSTRUCTION: "Under construction",
};

const EMPTY: StructuralAssessment = { assessmentStatus: "pending" };

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-ink-faint">{label}</label>
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
      />
    </div>
  );
}

function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null | undefined;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" checked={value ?? false} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

export function StructuralAssessmentSection({ job }: { job: VendorJob }) {
  const save = useSaveStructuralAssessment(job.id);
  const [a, setA] = useState<StructuralAssessment>(job.structuralAssessment ?? EMPTY);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";
  const set = <K extends keyof StructuralAssessment>(key: K, value: StructuralAssessment[K]) => setA((prev) => ({ ...prev, [key]: value }));

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Structural assessment</h2>
        <Badge tone={a.assessmentStatus === "complete" ? "blue" : "neutral"}>
          {a.assessmentStatus === "complete" ? "Complete" : a.assessmentStatus === "needs_engineer" ? "Needs engineer" : "Pending"}
        </Badge>
      </div>

      <fieldset disabled={!editable} className="space-y-4 disabled:opacity-60">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Roof structural type</label>
            <input
              value={a.roofStructuralType ?? ""}
              onChange={(e) => set("roofStructuralType", e.target.value)}
              placeholder="e.g. RCC frame + slab"
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <NumberField label="RCC slab thickness (mm)" value={a.rccSlabThicknessMm} onChange={(v) => set("rccSlabThicknessMm", v)} />
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Structural condition</label>
            <select
              value={a.structuralCondition ?? ""}
              onChange={(e) => set("structuralCondition", (e.target.value || null) as StructuralCondition | null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not assessed</option>
              {(Object.keys(CONDITION_LABEL) as StructuralCondition[]).map((c) => (
                <option key={c} value={c}>
                  {CONDITION_LABEL[c]}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Recommended mounting structure</label>
            <input
              value={a.recommendedMountingStructure ?? ""}
              onChange={(e) => set("recommendedMountingStructure", e.target.value)}
              placeholder="e.g. hot-dip galvanized elevated"
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <BoolField label="Cracks present" value={a.hasCracks} onChange={(v) => set("hasCracks", v)} />
          <BoolField label="Water leakage" value={a.hasWaterLeakage} onChange={(v) => set("hasWaterLeakage", v)} />
          <BoolField label="Corrosion" value={a.hasCorrosion} onChange={(v) => set("hasCorrosion", v)} />
          <BoolField label="Structural damage" value={a.hasStructuralDamage} onChange={(v) => set("hasStructuralDamage", v)} />
        </div>

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Load considerations</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <NumberField label="Existing load (kg/m²)" value={a.existingLoadKgM2} onChange={(v) => set("existingLoadKgM2", v)} />
            <NumberField label="Additional load capacity (kg/m²)" value={a.additionalLoadCapacityKgM2} onChange={(v) => set("additionalLoadCapacityKgM2", v)} />
            <NumberField label="Roof load capacity (kg/m²)" value={a.roofLoadCapacityKgM2} onChange={(v) => set("roofLoadCapacityKgM2", v)} />
            <NumberField label="Estimated panel weight (kg)" value={a.estimatedPanelWeightKg} onChange={(v) => set("estimatedPanelWeightKg", v)} />
            <NumberField label="Mounting structure weight (kg)" value={a.mountingStructureWeightKg} onChange={(v) => set("mountingStructureWeightKg", v)} />
            <NumberField label="Total additional load (kg)" value={a.totalAdditionalLoadKg} onChange={(v) => set("totalAdditionalLoadKg", v)} />
            <NumberField label="Load per m² (kg)" value={a.loadPerSqmKg} onChange={(v) => set("loadPerSqmKg", v)} />
            <NumberField label="Safety margin (%)" value={a.safetyMarginPct} onChange={(v) => set("safetyMarginPct", v)} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <BoolField label="Inspection required" value={a.inspectionRequired} onChange={(v) => set("inspectionRequired", v)} />
          <BoolField label="Engineer approval required" value={a.engineerApprovalRequired} onChange={(v) => set("engineerApprovalRequired", v)} />
          <BoolField label="Structural certificate available" value={a.structuralCertificateAvailable} onChange={(v) => set("structuralCertificateAvailable", v)} />
        </div>

        <div>
          <label className="mb-1 block text-xs text-ink-faint">Assessment status</label>
          <select
            value={a.assessmentStatus}
            onChange={(e) => set("assessmentStatus", e.target.value as StructuralAssessment["assessmentStatus"])}
            className="w-full max-w-xs rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          >
            <option value="pending">Pending</option>
            <option value="complete">Complete</option>
            <option value="needs_engineer">Needs engineer</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs text-ink-faint">Notes</label>
          <textarea
            value={a.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={2}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
      </fieldset>

      {editable && (
        <Button size="sm" onClick={() => save.mutate(a)} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save assessment"}
        </Button>
      )}
    </Card>
  );
}
