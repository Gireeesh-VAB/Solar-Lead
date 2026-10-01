"use client";

import { useState } from "react";
import { Card, Button } from "@/components/ui/Primitives";
import { useSaveBatteryAssessment } from "@/lib/query/hooks";
import type { BatteryTechnology, BatteryAssessment, VendorJob } from "@/lib/types";

const EMPTY: BatteryAssessment = {};

const TECH_LABEL: Record<BatteryTechnology, string> = {
  LITHIUM_ION: "Lithium-ion",
  LEAD_ACID: "Lead-acid",
  OTHER: "Other",
};

export function BatteryAssessmentSection({ job }: { job: VendorJob }) {
  const save = useSaveBatteryAssessment(job.id);
  const [a, setA] = useState<BatteryAssessment>(job.batteryAssessment ?? EMPTY);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";
  const set = <K extends keyof BatteryAssessment>(key: K, value: BatteryAssessment[K]) => setA((prev) => ({ ...prev, [key]: value }));

  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Battery assessment</h2>

      <fieldset disabled={!editable} className="space-y-4 disabled:opacity-60">
        <div className="grid grid-cols-2 gap-2">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={a.batteryRoomAvailable ?? false} onChange={(e) => set("batteryRoomAvailable", e.target.checked)} />
            Battery room available
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={a.ventilationAvailable ?? false} onChange={(e) => set("ventilationAvailable", e.target.checked)} />
            Ventilation available
          </label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Battery location</label>
            <input
              value={a.batteryLocation ?? ""}
              onChange={(e) => set("batteryLocation", e.target.value)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Fire safety measures</label>
            <input
              value={a.fireSafetyMeasures ?? ""}
              onChange={(e) => set("fireSafetyMeasures", e.target.value)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Recommended capacity (kWh)</label>
            <input
              type="number"
              min={0}
              value={a.recommendedBatteryCapacityKwh ?? ""}
              onChange={(e) => set("recommendedBatteryCapacityKwh", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Recommended technology</label>
            <select
              value={a.recommendedBatteryTechnology ?? ""}
              onChange={(e) => set("recommendedBatteryTechnology", (e.target.value || null) as BatteryTechnology | null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            >
              <option value="">Not specified</option>
              {(Object.keys(TECH_LABEL) as BatteryTechnology[]).map((t) => (
                <option key={t} value={t}>
                  {TECH_LABEL[t]}
                </option>
              ))}
            </select>
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
