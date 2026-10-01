"use client";

// The result page's satellite map, plus this app's own packed solar-panel
// layout drawn on top of it (engine/panel_packing.py) — panels laid inside
// the resolved usable roof polygon, avoiding obstacles and roof edges, and
// capped at the recommended system size shown elsewhere on the page.
//
// A client component purely so the panel layout can be fetched WITHOUT
// blocking the page: the result — verdict, capacity, survey status — is
// server-rendered and must not wait on this round trip, nor break if it
// fails. The map paints immediately; panels appear when they arrive, or
// never, and nothing else on the page notices.

import { useState } from "react";
import Link from "next/link";
import { Loader2, PenLine } from "lucide-react";
import { MapView, type MapPinData } from "@/components/map/MapView";
import type { LayerVisibility, RoofSegmentPolygon } from "@/components/map/SolarPanelOverlay";
import { useCheckObstacles, useCheckSolarLayout } from "@/lib/query/hooks";
import { cn, polygonAreaM2 } from "@/lib/utils";

const DEFAULT_VISIBILITY: LayerVisibility = {
  panels: true,
  obstacles: true,
  restrictedZones: true,
  segments: true,
};

export function ResultMap({
  checkId,
  pin,
  roofBoundary,
  boundaryIsApproximate = true,
  canEditBoundary = false,
  usableAreaM2,
  restrictedZones = [],
  roofSegments = [],
  height = 300,
}: {
  checkId: string;
  pin: MapPinData;
  /** The roof GEO-04 detected, from the check itself. Outlined on the map
   *  so the panels can be read as belonging to a specific footprint. */
  roofBoundary?: { lat: number; lng: number }[];
  /** Whether that outline is Google's bounding box rather than a traced
   *  roof. Changes what we are willing to claim about it. */
  boundaryIsApproximate?: boolean;
  /** Offer the trace step. Only meaningful when there is a shape to
   *  correct — with no boundary at all there is nothing to drag. */
  canEditBoundary?: boolean;
  /** engine/area.py's post-setback, post-exclusion usable roof figure —
   *  the denominator for the coverage % shown below the panel count.
   *  Undefined/zero just omits that clause, never divides by it. */
  usableAreaM2?: number | null;
  /** Site.exclusions rings — the real setback + applied-obstacle geometry
   *  already subtracted from the usable area. Empty draws nothing. */
  restrictedZones?: { lat: number; lng: number }[][];
  /** Each roof plane's own polygon (Step 14) — see RoofInfoCard for
   *  the text-list version of the same data. Segments without a
   *  polygon (parseRoofSegments already filters these) are never
   *  passed in — this component only draws real shapes. */
  roofSegments?: RoofSegmentPolygon[];
  height?: number;
}) {
  const { data, isLoading, isError } = useCheckSolarLayout(checkId);
  const { data: obstacleData } = useCheckObstacles(checkId);
  const [visibility, setVisibility] = useState<LayerVisibility>(DEFAULT_VISIBILITY);

  const panels = data?.status === "ok" ? data.panels : undefined;
  const obstacles = obstacleData?.obstacles ?? [];

  const toggle = (key: keyof LayerVisibility) =>
    setVisibility((prev) => ({ ...prev, [key]: !prev[key] }));

  const LAYER_TOGGLES: { key: keyof LayerVisibility; label: string; count: number }[] = [
    { key: "panels", label: "Panels", count: panels?.length ?? 0 },
    { key: "obstacles", label: "Obstacles", count: obstacles.length },
    { key: "restrictedZones", label: "Restricted zones", count: restrictedZones.length },
    { key: "segments", label: "Roof segments", count: roofSegments.length },
  ];

  return (
    <div>
      <MapView
        pins={[pin]}
        height={height}
        solarPanels={panels}
        roofObstacles={obstacles}
        restrictedZones={restrictedZones}
        roofSegments={roofSegments}
        roofBoundary={roofBoundary}
        layerVisibility={visibility}
      />

      {LAYER_TOGGLES.some((l) => l.count > 0) && (
        <div className="mt-1.5 flex flex-wrap gap-1.5" role="group" aria-label="Toggle map layers">
          {LAYER_TOGGLES.filter((l) => l.count > 0).map((layer) => (
            <button
              key={layer.key}
              type="button"
              onClick={() => toggle(layer.key)}
              aria-pressed={visibility[layer.key]}
              className={cn(
                "rounded-[3px] border px-2 py-1 text-[11px] font-medium transition-colors",
                visibility[layer.key]
                  ? "border-blue bg-[var(--surface-2)] text-blue"
                  : "border-line text-ink-faint hover:text-ink-soft"
              )}
            >
              {layer.label} ({layer.count})
            </button>
          ))}
        </div>
      )}

      {isLoading && (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-faint">
          <Loader2 size={12} strokeWidth={1.75} className="animate-spin" aria-hidden="true" />
          Loading panel layout…
        </p>
      )}

      {roofBoundary && roofBoundary.length >= 3 && (
        <p className="mt-1.5 text-xs text-ink-faint">
          {boundaryIsApproximate ? (
            <>
              The cyan outline is an <span className="font-medium text-ink-soft">approximate</span>{" "}
              area from satellite data — a rectangle around your building, not a traced roof. If
              your roof is an L-shape or an unusual shape, the surveyor will measure it properly
              and the layout will be corrected.
            </>
          ) : (
            <>The cyan outline is your surveyed roof. Panels are placed inside it.</>
          )}
        </p>
      )}

      {roofSegments.length > 1 && (
        <p className="mt-1.5 text-xs text-ink-faint">
          The <span className="font-medium text-ink-soft">coloured regions</span> are your roof&apos;s
          {" "}{roofSegments.length} separate planes — tap one to see its own direction and pitch.
        </p>
      )}

      {canEditBoundary && boundaryIsApproximate && (
        <Link
          href={`/check/${checkId}/boundary`}
          className="mt-2 inline-flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-xs font-medium text-blue transition-colors hover:border-blue hover:bg-surface"
        >
          <PenLine size={13} strokeWidth={1.75} aria-hidden="true" />
          Not quite right? Correct your roof outline
        </Link>
      )}

      {panels && panels.length > 0 && (
        <p className="mt-1.5 text-xs text-ink-faint">
          <span className="font-medium text-ink-soft">
            {data!.panelCount} panels shown ({data!.totalKwp.toFixed(1)} kWp)
          </span>{" "}
          — a preliminary layout for the recommended system size, placed inside the roof outline
          above and clear of any detected obstacles. A site survey confirms the final placement.
          {usableAreaM2 && usableAreaM2 > 0 && (
            <>
              {" "}
              That&apos;s about{" "}
              <span className="font-medium text-ink-soft">
                {Math.round(
                  (100 * panels.reduce((sum, p) => sum + polygonAreaM2(p.corners), 0)) / usableAreaM2,
                )}
                %
              </span>{" "}
              of your usable roof area.
            </>
          )}
        </p>
      )}

      {/* OBS-04. Only claim a clear roof when something actually looked:
          detection needs an OPENAI_API_KEY, and reporting "no obstacles"
          when the detector never ran would be a lie of omission. */}
      {obstacles.length > 0 && (
        <p className="mt-1 text-xs text-ink-faint">
          <span className="font-medium text-ink-soft">
            {obstacles.length} rooftop obstacle{obstacles.length === 1 ? "" : "s"}
          </span>{" "}
          shown in amber — these areas are excluded from the usable roof space.
        </p>
      )}
      {obstacleData && !obstacleData.detected && obstacleData.reason && (
        <p className="mt-1 text-xs text-ink-faint">
          Rooftop obstacles (water tanks, vents, existing panels) haven&apos;t been surveyed for
          this roof yet.
        </p>
      )}

      {/* An absent layout is stated, never papered over with drawn-on
          rectangles. The map underneath is still the customer's real roof. */}
      {!isLoading && !panels && (
        <p className="mt-1.5 text-xs text-ink-faint">
          {isError
            ? "Panel layout unavailable right now."
            : "Solar panel layout unavailable for this rooftop."}
        </p>
      )}
    </div>
  );
}
