"use client";

import { useState } from "react";
import { Card, Button } from "@/components/ui/Primitives";
import { useSaveInstallationConstraints } from "@/lib/query/hooks";
import type { InstallationConstraints, VendorJob } from "@/lib/types";

const EMPTY: InstallationConstraints = {};

const CHECKS: { key: keyof InstallationConstraints; label: string }[] = [
  { key: "roofAccessAvailable", label: "Roof access available" },
  { key: "staircaseAvailable", label: "Staircase available" },
  { key: "liftAvailable", label: "Lift available" },
  { key: "materialTransportationPossible", label: "Material transportation possible" },
  { key: "craneRequired", label: "Crane required" },
  { key: "ladderAccess", label: "Ladder access" },
  { key: "roofEntryPermission", label: "Roof entry permission" },
  { key: "workingSpaceAvailable", label: "Working space available" },
  { key: "panelCleaningAccess", label: "Panel cleaning access" },
  { key: "maintenanceAccess", label: "Maintenance access" },
  { key: "fireAccess", label: "Fire access" },
  { key: "emergencyAccess", label: "Emergency access" },
];

export function InstallationConstraintsSection({ job }: { job: VendorJob }) {
  const save = useSaveInstallationConstraints(job.id);
  const [c, setC] = useState<InstallationConstraints>(job.installationConstraints ?? EMPTY);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";

  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Installation constraints</h2>

      <fieldset disabled={!editable} className="space-y-4 disabled:opacity-60">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {CHECKS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-2 text-sm text-ink">
              <input
                type="checkbox"
                checked={(c[key] as boolean) ?? false}
                onChange={(e) => setC((prev) => ({ ...prev, [key]: e.target.checked }))}
              />
              {label}
            </label>
          ))}
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Installation pathway</label>
          <input
            value={c.installationPathway ?? ""}
            onChange={(e) => setC((prev) => ({ ...prev, installationPathway: e.target.value }))}
            placeholder="e.g. via internal staircase, no obstructions"
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Notes</label>
          <textarea
            value={c.notes ?? ""}
            onChange={(e) => setC((prev) => ({ ...prev, notes: e.target.value }))}
            rows={2}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
      </fieldset>

      {editable && (
        <Button size="sm" onClick={() => save.mutate(c)} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save constraints"}
        </Button>
      )}
    </Card>
  );
}
