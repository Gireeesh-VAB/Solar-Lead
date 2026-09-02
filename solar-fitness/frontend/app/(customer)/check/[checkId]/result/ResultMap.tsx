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
import { useCheckSolarLayout } from "@/lib/query/hooks";

export function ResultMap({
  checkId,
  pin,
  height = 300,
}: {
  checkId: string;
  pin: MapPinData;
  height?: number;
}) {
  const { data, isLoading, isError } = useCheckSolarLayout(checkId);

  const panels = data?.status === "ok" ? data.panels : undefined;

  return (
    <div>
      <MapView pins={[pin]} height={height} solarPanels={panels} />

      {/* The overlay's own caption. Google's panel count is NOT the system
          size shown above — that is P2's figure, reached a different way,
          and the two disagree. Labelling the source keeps them separate. */}
      {isLoading && (
        <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-faint">
          <Loader2 size={12} strokeWidth={1.75} className="animate-spin" aria-hidden="true" />
          Loading panel layout…
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
