"use client";

// "Is this your roof?" — the step that turns GEO-04's approximate
// rectangle into the actual roof outline.
//
// Until someone confirms or corrects it, every downstream number rests
// on a box drawn around the building: usable area, capacity, and where
// the panels land. Saving here stores a manual_polygon (GEO-01
// precedence 300), which outranks the Solar API rectangle (100) and
// becomes the authoritative geometry for every future assessment.

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Loader2, Plus, RotateCcw, TriangleAlert } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { Button } from "@/components/ui/Primitives";
import * as api from "@/lib/api/client";
import { approxAreaM2 } from "@/lib/geo/area";
import type { Site } from "@/lib/types";

export function BoundaryEditorClient({ check }: { check: Site }) {
  const router = useRouter();
  const original = useMemo<LatLngPoint[]>(() => check.boundary ?? [], [check.boundary]);

  const [points, setPoints] = useState<LatLngPoint[]>(original);
  const [version, setVersion] = useState(0);
  const [addPointSignal, setAddPointSignal] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onChange = useCallback((next: LatLngPoint[]) => setPoints(next), []);

  const area = approxAreaM2(points);
  // A roof smaller than this is almost certainly a mis-drag, not a
  // building — worth catching before it becomes someone's system size.
  const tooSmall = points.length >= 3 && area < 5;
  const canSave = points.length >= 3 && !tooSmall && !saving;

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      await api.saveCheckBoundary(check.id, points);
      // The boundary is versioned immediately, but usable area and
      // capacity are recomputed by the assessment. Rather than re-running
      // it here and again after the obstacle step, hand straight over to
      // that step — it ends with the same completeCheck() and lands on
      // the result. One recompute, from the finished geometry.
      router.push(`/check/${check.id}/obstacles`);
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Couldn't save the boundary. Please try again."
      );
      setSaving(false);
    }
  };

  if (original.length < 3) {
    return (
      <div className="rounded-[var(--radius-app)] border border-dashed border-line bg-surface p-6 text-center">
        <p className="text-sm text-ink-soft">
          We haven&apos;t detected a roof outline for this location yet, so there&apos;s nothing to
          correct. A surveyor will measure it during the site visit.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">Is this your roof?</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
          The cyan shape is our best guess from satellite data — a rectangle around your building,
          not a traced roof. Drag the corners onto your actual roof edges. For an L-shape, T-shape,
          or other irregular roof, drag one of the small midpoint handles out to create a new
          corner, or use &quot;Add point&quot; below.
        </p>
      </div>

      <MapView
        pins={[
          {
            id: check.id,
            lat: check.location.lat,
            lng: check.location.lng,
            label: check.name,
          },
        ]}
        // Fills most of the viewport on a small phone (where every pixel of
        // drag precision matters) without overflowing the layout on a
        // larger screen — a fixed px height was either cramped on mobile
        // or needlessly tall on desktop.
        height="clamp(320px, 60dvh, 480px)"
        editableBoundary={original}
        onBoundaryChange={onChange}
        editorVersion={version}
        addPointSignal={addPointSignal}
      />

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-ink-faint">
        <span>
          {points.length} corners · roughly{" "}
          <span className="font-medium text-ink-soft">{Math.round(area).toLocaleString()} m²</span>
        </span>
        <span>Right-click a corner to remove it.</span>
      </div>

      <Button
        type="button"
        variant="secondary"
        className="w-full"
        onClick={() => setAddPointSignal((n) => n + 1)}
        disabled={saving || points.length < 3}
      >
        <Plus size={16} strokeWidth={1.75} aria-hidden="true" /> Add point
      </Button>

      {tooSmall && (
        <p
          className="flex items-start gap-2 rounded-[var(--radius-app)] border px-3 py-2 text-xs"
          role="alert"
          style={{ borderColor: "var(--warn)", color: "var(--warn)" }}
        >
          <TriangleAlert size={14} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          That shape is too small to be a roof. Drag the corners back out before saving.
        </p>
      )}

      {error && (
        <p
          className="rounded-[var(--radius-app)] border px-3 py-2 text-xs"
          role="alert"
          style={{ borderColor: "var(--bad)", color: "var(--bad)" }}
        >
          {error}
        </p>
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          variant="secondary"
          className="flex-1"
          onClick={() => {
            setPoints(original);
            setVersion((v) => v + 1);
          }}
          disabled={saving}
        >
          <RotateCcw size={16} strokeWidth={1.75} aria-hidden="true" /> Start again
        </Button>
        <Button className="flex-1" onClick={save} disabled={!canSave}>
          {saving ? (
            <>
              <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Saving…
            </>
          ) : (
            <>
              <Check size={16} strokeWidth={1.75} aria-hidden="true" /> Confirm this roof
            </>
          )}
        </Button>
      </div>

      <p className="text-xs text-ink-faint">
        Confirming replaces the satellite estimate with your outline. Next we&apos;ll ask what&apos;s
        on the roof, then recalculate your usable roof space and system size from both.
      </p>
    </div>
  );
}
