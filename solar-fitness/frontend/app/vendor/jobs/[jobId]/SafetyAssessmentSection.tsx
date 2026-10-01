"use client";

import { useState } from "react";
import { Card, Button } from "@/components/ui/Primitives";
import { useSaveSafetyAssessment } from "@/lib/query/hooks";
import type { FireRisk, SafetyAssessment, VendorJob } from "@/lib/types";

const EMPTY: SafetyAssessment = {};

const ELECTRICAL_CHECKS: { key: keyof SafetyAssessment; label: string }[] = [
  { key: "properEarthing", label: "Proper earthing" },
  { key: "lightningProtection", label: "Lightning protection" },
  { key: "surgeProtection", label: "Surge protection" },
  { key: "dcIsolator", label: "DC isolator" },
  { key: "acIsolator", label: "AC isolator" },
  { key: "properCableRouting", label: "Proper cable routing" },
  { key: "cableProtection", label: "Cable protection" },
];

const PHYSICAL_CHECKS: { key: keyof SafetyAssessment; label: string }[] = [
  { key: "parapetWall", label: "Parapet wall" },
  { key: "fallProtection", label: "Fall protection" },
  { key: "safeRoofAccess", label: "Safe roof access" },
  { key: "walkwayAvailable", label: "Walkway available" },
  { key: "panelMaintenanceClearance", label: "Panel maintenance clearance" },
  { key: "structuralStability", label: "Structural stability" },
];

const FIRE_RISK_LABEL: Record<FireRisk, string> = { low: "Low", medium: "Medium", high: "High" };

function CheckGroup({
  title,
  checks,
  values,
  onChange,
}: {
  title: string;
  checks: { key: keyof SafetyAssessment; label: string }[];
  values: SafetyAssessment;
  onChange: (key: keyof SafetyAssessment, v: boolean) => void;
}) {
  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">{title}</h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {checks.map(({ key, label }) => (
          <label key={key} className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={(values[key] as boolean) ?? false} onChange={(e) => onChange(key, e.target.checked)} />
            {label}
          </label>
        ))}
      </div>
    </div>
  );
}

export function SafetyAssessmentSection({ job }: { job: VendorJob }) {
  const save = useSaveSafetyAssessment(job.id);
  const [a, setA] = useState<SafetyAssessment>(job.safetyAssessment ?? EMPTY);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";
  const set = <K extends keyof SafetyAssessment>(key: K, value: SafetyAssessment[K]) => setA((prev) => ({ ...prev, [key]: value }));

  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Safety assessment</h2>

      <fieldset disabled={!editable} className="space-y-4 disabled:opacity-60">
        <CheckGroup title="Electrical safety" checks={ELECTRICAL_CHECKS} values={a} onChange={set} />
        <CheckGroup title="Physical safety" checks={PHYSICAL_CHECKS} values={a} onChange={set} />

        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Fire safety</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs text-ink-faint">Fire risk</label>
              <select
                value={a.fireRisk ?? ""}
                onChange={(e) => set("fireRisk", (e.target.value || null) as FireRisk | null)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              >
                <option value="">Not assessed</option>
                {(Object.keys(FIRE_RISK_LABEL) as FireRisk[]).map((r) => (
                  <option key={r} value={r}>
                    {FIRE_RISK_LABEL[r]}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 pt-5 text-sm text-ink">
              <input type="checkbox" checked={a.fireEquipmentAvailable ?? false} onChange={(e) => set("fireEquipmentAvailable", e.target.checked)} />
              Fire equipment available
            </label>
            <label className="flex items-center gap-2 pt-5 text-sm text-ink">
              <input type="checkbox" checked={a.emergencyAccess ?? false} onChange={(e) => set("emergencyAccess", e.target.checked)} />
              Emergency access
            </label>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs text-ink-faint">Inverter location</label>
              <input
                value={a.inverterLocation ?? ""}
                onChange={(e) => set("inverterLocation", e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-ink-faint">Battery location (if applicable)</label>
              <input
                value={a.batteryLocation ?? ""}
                onChange={(e) => set("batteryLocation", e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              />
            </div>
          </div>
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
