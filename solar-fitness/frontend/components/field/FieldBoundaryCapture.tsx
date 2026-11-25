"use client";

// Vendor capture page's "Boundary" tab — the surveyor's own on-site trace
// of the real roof outline, saved as `field_measured` geometry (GEO-09's
// highest-trust source, see routers/app_vendor.py::submit_field_boundary).
//
// Same click-to-place-corner drawing as the customer-facing Freehand mode
// (components/map/BuildingSelector.tsx's Freehand tool) — reuses that
// exact FreehandPolygonSelector component rather than a second
// implementation, and the same two-step "Finish boundary" (closes the
// ring, switches to drag-to-adjust) then "Submit" flow.

import { useState } from "react";
import { Check, Plus, RefreshCcw } from "lucide-react";
import { FreehandPolygonSelector } from "@/components/map/FreehandPolygonSelector";
import { MapView } from "@/components/map/MapView";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { Button } from "@/components/ui/Primitives";
import { useSubmitFieldBoundary } from "@/lib/query/hooks";
import type { Site } from "@/lib/types";

export function FieldBoundaryCapture({ jobId, site }: { jobId: string; site: Site }) {
  const [points, setPoints] = useState<LatLngPoint[]>([]);
  const [drawing, setDrawing] = useState(true);
  const [version, setVersion] = useState(0);
  const [addPointSignal, setAddPointSignal] = useState(0);
  const submit = useSubmitFieldBoundary(jobId);

  const reset = () => {
    setPoints([]);
    setDrawing(true);
    setVersion((v) => v + 1);
    submit.reset();
  };

  const finish = () => {
    if (points.length < 3) return;
    setDrawing(false);
  };

  return (
    <div className="space-y-4">
      <MapView
        pins={[{ id: site.id, lat: site.location.lat, lng: site.location.lng, label: site.name }]}
        center={site.location}
        height={360}
      >
        <FreehandPolygonSelector
          initial={points}
          onChange={setPoints}
          version={version}
          addPointSignal={addPointSignal}
          isDrawing={drawing}
        />
      </MapView>

      <p className="text-xs text-ink-soft">
        {drawing
          ? points.length === 0
            ? "Tap your roof's first corner to start."
            : points.length < 3
              ? `${points.length} point${points.length === 1 ? "" : "s"} placed — at least 3 needed to finish.`
              : `${points.length} points placed. Keep tapping to add more, or finish the boundary.`
          : `${points.length} corners. Drag any point to fine-tune it.`}
      </p>

      {!drawing && (
        <Button size="md" variant="secondary" onClick={() => setAddPointSignal((n) => n + 1)} className="w-full min-h-[48px]">
          <Plus size={18} strokeWidth={1.75} /> Add point
        </Button>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Button size="md" variant="secondary" onClick={reset} className="min-h-[56px] text-base">
          <RefreshCcw size={18} strokeWidth={1.75} /> Reset
        </Button>
        {drawing ? (
          <Button size="md" onClick={finish} disabled={points.length < 3} className="min-h-[56px] text-base">
            <Check size={18} strokeWidth={1.75} /> Finish boundary
          </Button>
        ) : (
          <Button
            size="md"
            onClick={() => submit.mutate(points)}
            disabled={points.length < 3 || submit.isPending}
            className="min-h-[56px] text-base"
          >
            <Check size={18} strokeWidth={1.75} /> {submit.isPending ? "Submitting…" : "Submit boundary"}
          </Button>
        )}
      </div>

      {submit.isError && <p className="text-xs text-bad">{(submit.error as Error).message}</p>}
      {submit.isSuccess && (
        <p
          className="rounded-[var(--radius-app)] border p-3 text-sm"
          style={{ borderColor: "var(--good)", background: "var(--good-bg)", color: "var(--good)" }}
        >
          Boundary captured and saved.
        </p>
      )}
    </div>
  );
}
