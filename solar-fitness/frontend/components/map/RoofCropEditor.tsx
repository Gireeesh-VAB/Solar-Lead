"use client";

// StartCheckWizard step "adjust-boundary" — fine-tune the shape the
// "Select Building" step handed off (a resolved building, a crop
// fallback rectangle, or a Freehand trace) before it becomes the final
// analysis boundary.
//
// Thin premium chrome around the map/editor pair that already does the
// real work: MapView's editableBoundary mode + RoofBoundaryEditor (native
// google.maps.Polygon vertex/midpoint editing). The same pair already
// ships post-creation on /check/{id}/boundary ("is this your roof?") —
// this wraps it for the pre-creation wizard instead of duplicating it,
// sharing lib/geo/area.ts's area check with that page too.
//
// Chrome is corner-anchored (instructions top-left, actions bottom-
// right), matching BuildingSelector — a full-width bar over the map
// blocks exactly the area a customer needs to drag a corner into if
// their roof sits near that edge of the viewport.

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, RefreshCcw, TriangleAlert } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { Button } from "@/components/ui/Primitives";
import { approxAreaM2, MIN_PLAUSIBLE_ROOF_AREA_M2 } from "@/lib/geo/area";

export function RoofCropEditor({
  center,
  initial,
  onConfirm,
  resetLabel = "Reset to detected",
  notice,
}: {
  center: { lat: number; lng: number };
  /** The shape handed off by the "Select Building" step — a resolved
   *  building (Crop mode), a crop-rectangle fallback, or a Freehand
   *  trace. Always the STARTING shape; edits happen locally until
   *  Confirm. */
  initial: LatLngPoint[];
  onConfirm: (points: LatLngPoint[]) => void;
  /** Matches the Reset button's copy to how `initial` was produced —
   *  "Reset to detected" reads oddly for a Freehand trace or a crop
   *  fallback rectangle that was never actually detected. */
  resetLabel?: string;
  /** Optional caller-supplied caveat shown in the toolbar — e.g. Crop's
   *  "no building found inside the crop" fallback notice. */
  notice?: string;
}) {
  const [points, setPoints] = useState<LatLngPoint[]>(initial);
  const [version, setVersion] = useState(0);

  const area = approxAreaM2(points);
  const tooSmall = points.length >= 3 && area < MIN_PLAUSIBLE_ROOF_AREA_M2;
  const canConfirm = points.length >= 3 && !tooSmall;

  return (
    <div className="relative h-full w-full">
      <MapView
        pins={[]}
        center={center}
        height="100%"
        editableBoundary={initial}
        onBoundaryChange={setPoints}
        editorVersion={version}
      />

      {/* Instructions, top-left. */}
      <div className="pointer-events-none absolute left-4 top-4 max-w-[calc(100%-2rem)]">
        <div className="w-72 max-w-full space-y-2 rounded-xl border border-line bg-paper/97 p-3 shadow-lg backdrop-blur-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Adjust boundary
          </p>
          <p className="text-xs leading-snug text-ink-soft">
            Drag the corners onto your roof edges. Drag a midpoint handle out to add a corner.
            Right-click a corner to remove it.
          </p>
          <AnimatePresence>
            {notice && (
              <motion.p
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="flex items-start gap-1.5 rounded-lg border px-2.5 py-2 text-xs"
                style={{ borderColor: "var(--warn)", color: "var(--warn)", background: "var(--warn-bg)" }}
              >
                <TriangleAlert size={13} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
                {notice}
              </motion.p>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Actions, bottom-right. */}
      <div className="pointer-events-none absolute bottom-6 right-4 max-w-[calc(100%-2rem)]">
        <div className="pointer-events-auto w-80 max-w-full space-y-2.5 rounded-xl border border-line bg-paper/97 p-3.5 shadow-lg backdrop-blur-sm">
          <div className="flex items-center justify-between text-xs text-ink-faint">
            <span className="font-medium text-ink">{points.length} corners</span>
            <span>
              Roughly{" "}
              <span className="font-medium text-ink-soft">{Math.round(area).toLocaleString()} m²</span>
            </span>
          </div>

          {tooSmall && (
            <p className="flex items-start gap-1.5 text-xs text-warn" role="alert">
              <TriangleAlert size={13} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
              That shape is too small to be a roof. Drag the corners back out before confirming.
            </p>
          )}

          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() => {
                setPoints(initial);
                setVersion((v) => v + 1);
              }}
            >
              <RefreshCcw size={14} strokeWidth={1.75} aria-hidden="true" /> {resetLabel}
            </Button>
            <Button size="sm" className="flex-1" onClick={() => onConfirm(points)} disabled={!canConfirm}>
              <Check size={14} strokeWidth={1.75} aria-hidden="true" /> Confirm rooftop
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
