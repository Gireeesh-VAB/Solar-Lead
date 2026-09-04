"use client";

// The result page's satellite map, plus Google's real solar-panel layout
// drawn on top of it.
//
// A client component purely so the panel layout can be fetched WITHOUT
// blocking the page: the result — verdict, capacity, survey status — is
// server-rendered and must not wait on a Solar API round trip, nor break
// if that call fails. The map paints immediately; panels appear when they
// arrive, or never, and nothing else on the page notices.

import { Loader2 } from "lucide-react";
import { MapView, type MapPinData } from "@/components/map/MapView";
import { useCheckObstacles, useCheckSolarLayout } from "@/lib/query/hooks";

export function ResultMap({
  checkId,
  pin,
  roofBoundary,
  height = 300,
}: {
  checkId: string;
  pin: MapPinData;
  /** The roof GEO-04 detected, from the check itself. Outlined on the map
   *  so the panels can be read as belonging to a specific footprint. */
  roofBoundary?: { lat: number; lng: number }[];
  height?: number;
}) {
  const { data, isLoading, isError } = useCheckSolarLayout(checkId);
  const { data: obstacleData } = useCheckObstacles(checkId);

  const panels = data?.status === "ok" ? data.panels : undefined;
  const obstacles = obstacleData?.obstacles ?? [];

  return (
    <div>
      <MapView
        pins={[pin]}
        height={height}
        solarPanels={panels}
        roofObstacles={obstacles}
        roofBoundary={roofBoundary}
      />

      {/* The overlay's own caption. Google's panel count is NOT the system
          size shown above — that is P2's figure, reached a different way,
          and the two disagree. Labelling the source keeps them separate. */}
      {isLoading && (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-faint">
          <Loader2 size={12} strokeWidth={1.75} className="animate-spin" aria-hidden="true" />
          Loading panel layout…
        </p>
      )}

      {roofBoundary && roofBoundary.length >= 3 && (
        <p className="mt-1.5 text-xs text-ink-faint">
          The cyan outline is the roof we detected — panels are placed inside it. On tall
          buildings it can look slightly offset from the photo, because the satellite imagery
          and the roof data were captured on different dates.
        </p>
      )}

      {panels && panels.length > 0 && (
        <p className="mt-1.5 text-xs text-ink-faint">
          <span className="font-medium text-ink-soft">
            {data!.panelCount} panels shown ({data!.totalKwp.toFixed(1)} kWp)
          </span>{" "}
          — indicative layout from the {data!.source}, drawn on satellite imagery. The system size
          above is our own assessment; a site survey confirms the final layout.
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
