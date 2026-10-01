"use client";

// "Is there anything on your roof?" — step 2 of confirming a roof, after
// the outline itself.
//
// The vision pipeline already detects water tanks, AC units and the like
// (OBS-01..04) and subtracts them from the usable area. But it needs an
// API key to have ever run, it works from one satellite photo, and it
// misses things. The person standing on the roof knows what's up there.
//
// Nothing here is a parallel obstacle system: a tap becomes a small
// square polygon server-side, goes through the same OBS-03 validation,
// and is unioned into the same site.exclusions with the same
// applied_obstacle_polygons provenance a detected obstacle gets. Which is
// why the list below shows detected and marked items in one style —
// `source` decides only whether the customer may remove it.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CircleHelp, Loader2, Trash2 } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import { Button } from "@/components/ui/Primitives";
import * as api from "@/lib/api/client";
import type { ObstacleType } from "@/lib/api/client";
import {
  useCheckObstacles,
  useMarkCheckObstacle,
  useUnmarkCheckObstacle,
} from "@/lib/query/hooks";
import type { Site } from "@/lib/types";
import { TYPE_META } from "../result/ObstructionsList";

// The order the palette reads in — commonest rooftop objects first, and
// "Other structure" last as the catch-all. The icons and labels are
// TYPE_META's own, not a second set: a marked water tank has to look
// exactly like a detected one on the result page.
const PALETTE: ObstacleType[] = [
  "water_tank",
  "hvac_unit",
  "chimney",
  "existing_solar_panel",
  "vent",
  "antenna",
  "other",
];

// engine/obstacles.py's own source value for a customer's placement —
// the only kind this screen may delete.
const CUSTOMER_MARKED = "customer_marked";

export function ObstacleMarkerClient({ check }: { check: Site }) {
  const router = useRouter();
  const { data, isLoading } = useCheckObstacles(check.id);
  const mark = useMarkCheckObstacle(check.id);
  const unmark = useUnmarkCheckObstacle(check.id);

  const [selected, setSelected] = useState<ObstacleType>("water_tank");
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  const obstacles = data?.obstacles ?? [];
  const busy = mark.isPending || unmark.isPending || finishing;

  const place = (lat: number, lng: number) => {
    setError(null);
    mark.mutate(
      { type: selected, lat, lng },
      {
        onError: (err) =>
          setError(
            err instanceof Error
              ? err.message
              : "Couldn't save that. Please try tapping again."
          ),
      }
    );
  };

  const remove = (obstacleId: string) => {
    setError(null);
    unmark.mutate(obstacleId, {
      onError: (err) =>
        setError(err instanceof Error ? err.message : "Couldn't remove that. Please try again."),
    });
  };

  const finish = async () => {
    setError(null);
    setFinishing(true);
    // Marking versions the geometry immediately, but usable area, system
    // size and savings are produced by the assessment — so re-run it,
    // exactly as BoundaryEditorClient does after a corrected outline,
    // rather than leaving the customer on numbers that ignore what they
    // just told us.
    await api.completeCheck(check.id).catch(() => null);
    router.push(`/check/${check.id}/result`);
    router.refresh();
  };

  if ((check.boundary?.length ?? 0) < 3) {
    return (
      <div className="rounded-[var(--radius-app)] border border-dashed border-line bg-surface p-6 text-center">
        <p className="text-sm text-ink-soft">
          We haven&apos;t got a roof outline for this location yet, so there&apos;s nothing to mark
          things on. A surveyor will record what&apos;s on the roof during the site visit.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">
          Is there anything on your roof?
        </h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
          A water tank, an AC unit, a chimney — anything solar panels can&apos;t sit on. Pick what it
          is, then tap where it is on your roof. We&apos;ll keep the panels clear of it.
        </p>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          1. What is it?
        </p>
        <div className="flex flex-wrap gap-2">
          {PALETTE.map((type) => {
            const { label, icon: Icon } = TYPE_META[type];
            const active = selected === type;
            return (
              <button
                key={type}
                type="button"
                onClick={() => setSelected(type)}
                aria-pressed={active}
                disabled={busy}
                className={
                  "flex items-center gap-1.5 rounded-[var(--radius-app)] border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-60 " +
                  (active
                    ? "border-blue bg-surface-2 text-blue"
                    : "border-line bg-paper text-ink-soft hover:border-blue hover:text-ink")
                }
              >
                <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
                {label}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          2. Where is it?
        </p>
        <MapView
          // No pin: this map is about the roof, not the address. `center`
          // frames it without MapView drawing a location marker that the
          // customer might mistake for one of their own placements.
          pins={[]}
          center={{ lat: check.location.lat, lng: check.location.lng }}
          height="clamp(320px, 55dvh, 460px)"
          roofBoundary={check.boundary ?? undefined}
          roofObstacles={obstacles.map((o) => ({ id: o.id, polygon: o.polygon }))}
          interactive
          onMove={place}
          draggableCursor="crosshair"
          hint={`Tap your roof where the ${TYPE_META[selected].label.toLowerCase()} is.`}
        />
      </div>

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          On your roof
        </p>
        {isLoading ? (
          <p className="flex items-center gap-1.5 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading…
          </p>
        ) : obstacles.length === 0 ? (
          <p className="rounded-[var(--radius-app)] border border-dashed border-line bg-surface px-3 py-3 text-sm text-ink-soft">
            Nothing marked yet. If your roof really is clear, that&apos;s good news — just continue.
          </p>
        ) : (
          <ul className="space-y-2.5">
            {obstacles.map((obstacle) => {
              const meta = obstacle.type ? TYPE_META[obstacle.type] : null;
              const Icon = meta?.icon ?? CircleHelp;
              const mine = obstacle.source === CUSTOMER_MARKED;
              return (
                <li key={obstacle.id} className="flex items-center gap-2.5 text-sm">
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-app)]"
                    style={{ background: "var(--surface-2)", color: "var(--amber)" }}
                    aria-hidden="true"
                  >
                    <Icon size={14} strokeWidth={1.75} />
                  </span>
                  <span className="text-ink">{meta?.label ?? "Something on the roof"}</span>
                  {mine ? (
                    <button
                      type="button"
                      onClick={() => remove(obstacle.id)}
                      disabled={busy}
                      aria-label={`Remove ${meta?.label ?? "this"}`}
                      className="ml-auto inline-flex items-center gap-1 rounded-[var(--radius-app)] px-2 py-1 text-xs text-ink-faint transition-colors hover:text-[var(--bad)] disabled:opacity-60"
                    >
                      <Trash2 size={13} strokeWidth={1.75} aria-hidden="true" /> Remove
                    </button>
                  ) : (
                    // Not removable here on purpose: reversing a pipeline
                    // detection is an audited path, not a customer tap.
                    <span className="ml-auto text-xs text-ink-faint">We spotted this one</span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {error && (
        <p
          className="rounded-[var(--radius-app)] border px-3 py-2 text-xs"
          role="alert"
          style={{ borderColor: "var(--bad)", color: "var(--bad)" }}
        >
          {error}
        </p>
      )}

      <Button className="w-full" onClick={finish} disabled={busy}>
        {finishing ? (
          <>
            <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Updating your result…
          </>
        ) : (
          <>
            Done <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </>
        )}
      </Button>

      <p className="text-xs text-ink-faint">
        Anything you mark is left out of the roof space we can use, so your panel count and savings
        are recalculated from what&apos;s really up there.
      </p>
    </div>
  );
}
