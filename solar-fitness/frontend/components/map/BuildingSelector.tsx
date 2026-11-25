"use client";

// StartCheckWizard step "select-building" — two ways to point at the
// actual building: Crop (draw/resize/reposition a rectangle, then let
// the backend identify the real building inside it) or Freehand (drag
// each of a starting 4-corner quad's corners onto the rooftop's actual
// corners).
//
// Neither mode's raw shape becomes the final analysis boundary directly:
//  - Crop is ONLY a locator. Its center is sent to resolve-building (the
//    same click-to-locate endpoint the single-tap flow used) to find the
//    real building; the rectangle itself is never assumed to be the roof.
//    If nothing resolves inside it, the rectangle's own corners become a
//    starting shape for the next (Adjust Boundary) step instead — an
//    explicit fallback, never a silent one (see `usedFallback` below).
//  - Freehand's 4 dragged corners ARE the candidate boundary — no backend
//    call — but still flow into the same Adjust Boundary step afterwards
//    for fine-tuning (including turning it into an L-shape), same as
//    Crop's resolved building does.
//
// Chrome is deliberately corner-anchored (toolbar top-left, actions
// bottom-right) rather than full-width bars across the top/bottom: a
// full-width instruction bar sitting over the map ate into the exact
// area a customer needs to click when their roof happens to be near the
// top or bottom edge of the viewport — on a small building that's most
// of the visible roof. Corner cards leave the map itself clickable.

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  Crop as CropIcon,
  Loader2,
  PenTool,
  Plus,
  RefreshCcw,
  TriangleAlert,
  X,
} from "lucide-react";
import { MapView } from "@/components/map/MapView";
import {
  CropRectangleSelector,
  defaultCropRect,
  rectCenter,
  rectToCorners,
  type RotatedRect,
} from "@/components/map/CropRectangleSelector";
import { FreehandPolygonSelector } from "@/components/map/FreehandPolygonSelector";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { Button } from "@/components/ui/Primitives";
import { cn } from "@/lib/utils";
import { useResolveBuildingAt } from "@/lib/query/hooks";

export interface BuildingSelectionResult {
  points: LatLngPoint[];
  method: "crop" | "freehand";
  source: "solar_api_mask" | "solar_api" | null;
  centroid: LatLngPoint;
  /** Crop found no building inside the rectangle — `points` is the
   *  rectangle's own corners, a starting shape to refine, not a result. */
  usedFallback: boolean;
  /** Google's imagery tier/capture date for this detection — null for
   *  Freehand (no Solar API resolution involved at all) or when Google
   *  didn't report one. Lets the "Adjust boundary" step warn when the
   *  auto-detected shape ran on old/lower-tier imagery, so the customer
   *  knows to check the edges rather than trust them blindly. */
  imageryQuality: string | null;
  imageryDate: string | null;
}

type Mode = "crop" | "freehand";

function averageOf(points: LatLngPoint[]): LatLngPoint {
  return {
    lat: points.reduce((s, p) => s + p.lat, 0) / points.length,
    lng: points.reduce((s, p) => s + p.lng, 0) / points.length,
  };
}

const panelMotion = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 8 },
  transition: { duration: 0.18 },
};

export function BuildingSelector({
  center,
  onConfirm,
}: {
  center: { lat: number; lng: number };
  /** Fires once the customer confirms a Crop or Freehand selection. */
  onConfirm: (result: BuildingSelectionResult) => void;
}) {
  const resolve = useResolveBuildingAt();
  const [mode, setMode] = useState<Mode>("crop");
  const [modeVersion, setModeVersion] = useState(0);

  const [cropRect, setCropRect] = useState<RotatedRect>(() => defaultCropRect(center));
  const [cropError, setCropError] = useState<string | null>(null);

  // Freehand starts empty — the customer places every point by clicking
  // the map (first click = first corner), rather than dragging a starting
  // shape into place.
  const [freehandPoints, setFreehandPoints] = useState<LatLngPoint[]>([]);
  const [freehandAddPointSignal, setFreehandAddPointSignal] = useState(0);
  // true while still placing points by clicking; false once "Finish
  // boundary" is pressed, which closes the ring and hands off to
  // drag-to-adjust (+ the "Add point" button) instead.
  const [freehandDrawing, setFreehandDrawing] = useState(true);

  /** Switches mode AND discards any in-progress shape — the deliberate
   *  "start over" action. A no-op when `next` is already the active mode:
   *  re-tapping the current tool must never silently wipe a trace the
   *  customer is mid-way through (this was a real bug — a stray tap on
   *  the toolbar looked exactly like "the tool stopped working"). Use
   *  `resetShape()` below for an explicit same-mode reset instead. */
  const switchMode = (next: Mode) => {
    if (next === mode) return;
    setMode(next);
    setModeVersion((v) => v + 1);
    setCropRect(defaultCropRect(center));
    setCropError(null);
    setFreehandPoints([]);
    setFreehandDrawing(true);
  };

  const resetShape = () => {
    setModeVersion((v) => v + 1);
    setCropRect(defaultCropRect(center));
    setCropError(null);
    setFreehandPoints([]);
    setFreehandDrawing(true);
  };

  /** "Finish boundary" — closes the ring (last point connects back to the
   *  first) and switches from click-to-add over to drag-to-adjust. Only
   *  reachable once there are enough points for a valid polygon; the
   *  button itself is disabled below the same threshold. */
  const finishFreehand = () => {
    if (freehandPoints.length < 3) return;
    setFreehandDrawing(false);
  };

  const cancelSelection = () => {
    // No neutral/no-tool state in this design — cancelling just resets
    // the active tool rather than leaving the map inert with nothing
    // selectable, which read as "broken" during review.
    resetShape();
  };

  const confirmCrop = () => {
    setCropError(null);
    const centerPoint = rectCenter(cropRect);
    resolve.mutate(
      { lat: centerPoint.lat, lng: centerPoint.lng },
      {
        onSuccess: (data) => {
          if (data.status === "ok" && data.boundary && data.boundary.length >= 3) {
            onConfirm({
              // The customer's own drawn rectangle — its exact dimensions
              // and angle — not Google's auto-detected outline. Detection
              // still ran (source/imagery fields below carry its result as
              // context), but its SHAPE is no longer used to replace what
              // the customer deliberately cropped; they asked for their
              // crop to be the starting shape they refine, not swapped out
              // from under them.
              points: rectToCorners(cropRect),
              method: "crop",
              source: data.source,
              // The crop rectangle's own centre, not data.centroid — since
              // the shown shape is now always the crop rectangle, the map
              // must centre on THAT, never on a different building's
              // centroid (the exact mismatch fixed earlier for the case
              // where the two shapes differed).
              centroid: centerPoint,
              usedFallback: false,
              imageryQuality: data.imageryQuality,
              imageryDate: data.imageryDate,
            });
          } else {
            setCropError(
              data.status === "no_coverage"
                ? "No building detected inside the crop — using the crop area as a starting shape. Adjust it to match your roof on the next step."
                : "Building detection is temporarily unavailable — using the crop area as a starting shape."
            );
            onConfirm({
              points: rectToCorners(cropRect),
              method: "crop",
              source: null,
              centroid: centerPoint,
              usedFallback: true,
              imageryQuality: null,
              imageryDate: null,
            });
          }
        },
        onError: () => {
          onConfirm({
            points: rectToCorners(cropRect),
            method: "crop",
            source: null,
            centroid: centerPoint,
            usedFallback: true,
            imageryQuality: null,
            imageryDate: null,
          });
        },
      }
    );
  };

  const closeFreehand = () => {
    if (freehandPoints.length < 3) return;
    onConfirm({
      points: freehandPoints,
      method: "freehand",
      source: null,
      centroid: averageOf(freehandPoints),
      usedFallback: false,
      // Freehand is the customer tracing directly over what they see —
      // no Solar API resolution involved, so no imagery-precision
      // caveat applies.
      imageryQuality: null,
      imageryDate: null,
    });
  };

  return (
    <div className="relative h-full w-full">
      <MapView pins={[]} center={center} height="100%">
        {mode === "crop" && (
          <CropRectangleSelector initialRect={cropRect} onChange={setCropRect} version={modeVersion} />
        )}
        {mode === "freehand" && (
          <FreehandPolygonSelector
            initial={freehandPoints}
            onChange={setFreehandPoints}
            version={modeVersion}
            addPointSignal={freehandAddPointSignal}
            isDrawing={freehandDrawing}
          />
        )}
      </MapView>

      {/* Toolbar, top-left — compact, so most of the map stays clickable.
          z-10 (below the wizard's own z-20 top bar) is belt-and-braces:
          this panel already lives in its own flex area below that bar, but
          an explicit stacking order means it can never paint over it even
          if that ever changes. */}
      <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-[calc(100%-2rem)]">
        <div className="pointer-events-auto w-72 max-w-full space-y-2 rounded-xl border border-line bg-paper/97 p-3 shadow-lg backdrop-blur-sm">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
            Select building
          </p>
          <div className="grid grid-cols-2 gap-1 rounded-lg bg-surface-2 p-1">
            <button
              type="button"
              onClick={() => switchMode("crop")}
              aria-pressed={mode === "crop"}
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-md py-2 text-xs font-semibold transition-colors",
                mode === "crop" ? "bg-paper text-ink shadow-sm" : "text-ink-faint hover:text-ink-soft"
              )}
            >
              <CropIcon size={14} strokeWidth={1.9} aria-hidden="true" /> Crop
            </button>
            <button
              type="button"
              onClick={() => switchMode("freehand")}
              aria-pressed={mode === "freehand"}
              className={cn(
                "flex items-center justify-center gap-1.5 rounded-md py-2 text-xs font-semibold transition-colors",
                mode === "freehand" ? "bg-paper text-ink shadow-sm" : "text-ink-faint hover:text-ink-soft"
              )}
            >
              <PenTool size={14} strokeWidth={1.9} aria-hidden="true" /> Freehand
            </button>
          </div>
          <AnimatePresence mode="wait">
            <motion.p key={`${mode}-${freehandDrawing}`} {...panelMotion} className="text-xs leading-snug text-ink-soft">
              {mode === "crop"
                ? "Drag the handles to resize, the outer dot to rotate, or the rectangle itself to reposition — cover your building."
                : freehandDrawing
                  ? "Click your roof's corners in order to trace its outline — rectangle, L-shape, or any irregular shape. Then finish the boundary."
                  : "Drag any point to fine-tune it. Use \"Add point\" to add more corners for an L-shaped or irregular roof."}
            </motion.p>
          </AnimatePresence>
        </div>
      </div>

      {/* Actions, bottom-right. */}
      <div className="pointer-events-none absolute bottom-6 right-4 z-10 max-w-[calc(100%-2rem)]">
        <AnimatePresence mode="wait">
          {mode === "crop" ? (
            <motion.div key="crop-actions" {...panelMotion} className="pointer-events-auto w-80 max-w-full">
              <div className="space-y-2.5 rounded-xl border border-line bg-paper/97 p-3.5 shadow-lg backdrop-blur-sm">
                {resolve.isPending ? (
                  <div className="flex items-center gap-2 text-sm text-ink">
                    <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                    Identifying the building inside the crop…
                  </div>
                ) : cropError ? (
                  <p className="flex items-start gap-1.5 text-xs text-warn">
                    <TriangleAlert size={13} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
                    {cropError}
                  </p>
                ) : (
                  <p className="text-xs text-ink-soft">
                    The rectangle only locates your building — it won&apos;t be used as the roof shape
                    itself.
                  </p>
                )}
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" className="flex-1" onClick={cancelSelection} disabled={resolve.isPending}>
                    <X size={14} strokeWidth={1.75} aria-hidden="true" /> Cancel
                  </Button>
                  <Button variant="secondary" size="sm" className="flex-1" onClick={resetShape} disabled={resolve.isPending}>
                    <RefreshCcw size={14} strokeWidth={1.75} aria-hidden="true" /> Reset
                  </Button>
                  <Button size="sm" className="flex-1" onClick={confirmCrop} disabled={resolve.isPending}>
                    <Check size={14} strokeWidth={1.75} aria-hidden="true" /> Confirm
                  </Button>
                </div>
              </div>
            </motion.div>
          ) : (
            <motion.div key="freehand-actions" {...panelMotion} className="pointer-events-auto w-80 max-w-full">
              <div className="space-y-2.5 rounded-xl border border-line bg-paper/97 p-3.5 shadow-lg backdrop-blur-sm">
                {freehandDrawing ? (
                  <p className="text-xs text-ink-soft">
                    {freehandPoints.length === 0
                      ? "Click your roof's first corner to start."
                      : freehandPoints.length < 3
                        ? `${freehandPoints.length} point${freehandPoints.length === 1 ? "" : "s"} placed — at least 3 needed to finish.`
                        : `${freehandPoints.length} points placed. Keep clicking to add more, or finish the boundary.`}
                  </p>
                ) : (
                  <p className="text-xs text-ink-soft">
                    {freehandPoints.length} corners. You can also fine-tune further on the next step.
                  </p>
                )}
                {!freehandDrawing && (
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full"
                    onClick={() => setFreehandAddPointSignal((n) => n + 1)}
                  >
                    <Plus size={14} strokeWidth={1.75} aria-hidden="true" /> Add point
                  </Button>
                )}
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" className="flex-1" onClick={cancelSelection}>
                    <X size={14} strokeWidth={1.75} aria-hidden="true" /> Cancel
                  </Button>
                  <Button variant="secondary" size="sm" className="flex-1" onClick={resetShape}>
                    <RefreshCcw size={14} strokeWidth={1.75} aria-hidden="true" /> Reset
                  </Button>
                  {freehandDrawing ? (
                    <Button
                      size="sm"
                      className="flex-1"
                      onClick={finishFreehand}
                      disabled={freehandPoints.length < 3}
                    >
                      <Check size={14} strokeWidth={1.75} aria-hidden="true" /> Finish boundary
                    </Button>
                  ) : (
                    <Button size="sm" className="flex-1" onClick={closeFreehand} disabled={freehandPoints.length < 3}>
                      <Check size={14} strokeWidth={1.75} aria-hidden="true" /> Confirm
                    </Button>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
