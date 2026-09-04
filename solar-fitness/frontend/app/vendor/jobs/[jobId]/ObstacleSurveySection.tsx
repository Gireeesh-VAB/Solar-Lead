"use client";

import { useState } from "react";
import { Plus, Trash2, Image as ImageIcon } from "lucide-react";
import { Card, Button, Badge } from "@/components/ui/Primitives";
import { useSaveObstacleSurvey } from "@/lib/query/hooks";
import type { ObstacleSurveyItem, ObstacleType, VendorJob } from "@/lib/types";

const OBSTACLE_TYPE_LABEL: Record<ObstacleType, string> = {
  WATER_TANK: "Water tank",
  OVERHEAD_TANK: "Overhead tank",
  STAIRCASE_ROOM: "Staircase room",
  LIFT_ROOM: "Lift room",
  SOLAR_WATER_HEATER: "Solar water heater",
  EXISTING_SOLAR_PANEL: "Existing solar panels",
  AC_OUTDOOR_UNIT: "AC outdoor units",
  PIPE: "Pipes",
  VENTILATION: "Ventilation system",
  ELECTRICAL_EQUIPMENT: "Electrical equipment",
  ANTENNA: "Antenna",
  SATELLITE_DISH: "Satellite dish",
  CHIMNEY: "Chimney",
  TREE: "Tree",
  ADJACENT_BUILDING: "Adjacent building",
  PARAPET_WALL: "Parapet wall",
  OTHER: "Other structure",
};

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function emptyObstacle(): ObstacleSurveyItem {
  return { id: crypto.randomUUID(), type: "OTHER" };
}

export function ObstacleSurveySection({ job }: { job: VendorJob }) {
  const save = useSaveObstacleSurvey(job.id);
  const [obstacles, setObstacles] = useState<ObstacleSurveyItem[]>(job.obstacleSurvey);
  const [draft, setDraft] = useState<ObstacleSurveyItem | null>(null);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";

  const persist = (next: ObstacleSurveyItem[]) => {
    setObstacles(next);
    save.mutate(next);
  };

  const removeObstacle = (id: string) => persist(obstacles.filter((o) => o.id !== id));

  const saveDraft = () => {
    if (!draft) return;
    persist([...obstacles, draft]);
    setDraft(null);
  };

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Obstacles ({obstacles.length})
        </h2>
        {editable && !draft && (
          <Button variant="secondary" size="sm" onClick={() => setDraft(emptyObstacle())}>
            <Plus size={13} strokeWidth={1.75} /> Add obstacle
          </Button>
        )}
      </div>

      {obstacles.length === 0 && !draft && (
        <p className="text-sm text-ink-soft">No obstacles recorded yet.</p>
      )}

      <ul className="space-y-2">
        {obstacles.map((o) => (
          <li key={o.id} className="flex items-start justify-between gap-3 rounded-[var(--radius-app)] border border-line px-3 py-2 text-sm">
            <div className="space-y-0.5">
              <p className="flex items-center gap-2 font-medium text-ink">
                {OBSTACLE_TYPE_LABEL[o.type]}
                {o.photoDataUrl && <ImageIcon size={13} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />}
              </p>
              <p className="text-xs text-ink-soft">
                {o.location && <span>{o.location} · </span>}
                {[o.lengthM && `L ${o.lengthM}m`, o.widthM && `W ${o.widthM}m`, o.heightM && `H ${o.heightM}m`, o.distanceFromEdgeM && `${o.distanceFromEdgeM}m from edge`]
                  .filter(Boolean)
                  .join(" · ") || "No measurements recorded"}
              </p>
              {o.notes && <p className="text-xs text-ink-faint">{o.notes}</p>}
            </div>
            {editable && (
              <button
                type="button"
                onClick={() => removeObstacle(o.id)}
                className="shrink-0 text-ink-faint hover:text-bad"
                aria-label={`Remove ${OBSTACLE_TYPE_LABEL[o.type]}`}
              >
                <Trash2 size={14} strokeWidth={1.75} />
              </button>
            )}
          </li>
        ))}
      </ul>

      {draft && (
        <div className="space-y-2 rounded-[var(--radius-app)] border border-dashed border-line p-3">
          <div className="grid grid-cols-2 gap-2">
            <select
              value={draft.type}
              onChange={(e) => setDraft({ ...draft, type: e.target.value as ObstacleType })}
              className="col-span-2 rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            >
              {(Object.keys(OBSTACLE_TYPE_LABEL) as ObstacleType[]).map((t) => (
                <option key={t} value={t}>
                  {OBSTACLE_TYPE_LABEL[t]}
                </option>
              ))}
            </select>
            <input
              placeholder="Location (e.g. north corner)"
              value={draft.location ?? ""}
              onChange={(e) => setDraft({ ...draft, location: e.target.value })}
              className="col-span-2 rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            <input
              type="number"
              placeholder="Length (m)"
              value={draft.lengthM ?? ""}
              onChange={(e) => setDraft({ ...draft, lengthM: e.target.value ? Number(e.target.value) : null })}
              className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            <input
              type="number"
              placeholder="Width (m)"
              value={draft.widthM ?? ""}
              onChange={(e) => setDraft({ ...draft, widthM: e.target.value ? Number(e.target.value) : null })}
              className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            <input
              type="number"
              placeholder="Height (m)"
              value={draft.heightM ?? ""}
              onChange={(e) => setDraft({ ...draft, heightM: e.target.value ? Number(e.target.value) : null })}
              className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            <input
              type="number"
              placeholder="Distance from edge (m)"
              value={draft.distanceFromEdgeM ?? ""}
              onChange={(e) => setDraft({ ...draft, distanceFromEdgeM: e.target.value ? Number(e.target.value) : null })}
              className="rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            <textarea
              placeholder="Notes"
              value={draft.notes ?? ""}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              className="col-span-2 rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              rows={2}
            />
            <label className="col-span-2 flex cursor-pointer items-center gap-2 text-xs text-ink-soft">
              <input
                type="file"
                accept="image/*"
                capture="environment"
                className="hidden"
                onChange={async (e) => {
                  const file = e.target.files?.[0];
                  if (file) setDraft({ ...draft, photoDataUrl: await readAsDataUrl(file) });
                }}
              />
              <span className="inline-flex items-center gap-1 rounded-[var(--radius-app)] border border-line px-2 py-1 hover:border-teal">
                <ImageIcon size={13} strokeWidth={1.75} /> {draft.photoDataUrl ? "Photo attached" : "Attach photo"}
              </span>
              {draft.photoDataUrl && <Badge tone="blue">Ready</Badge>}
            </label>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={saveDraft} disabled={save.isPending}>
              Save obstacle
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setDraft(null)}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
