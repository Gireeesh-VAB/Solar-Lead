"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  APIProvider,
  Map as GoogleMap,
  Marker,
  useMap,
} from "@vis.gl/react-google-maps";
import { MapPin } from "lucide-react";
import { SolarPanelOverlay, type SolarPanelPolygon } from "./SolarPanelOverlay";
import type { Verdict } from "@/lib/types";
import { VERDICT_LABEL } from "@/lib/utils";

export interface MapPinData {
  id: string;
  lat: number;
  lng: number;
  label: string;
  verdict?: Verdict;
}

const VERDICT_COLOR: Record<Verdict, string> = {
  SUITABLE: "var(--good)",
  SUITABLE_SUBJECT_TO_SURVEY: "var(--warn)",
  CONDITIONAL: "var(--warn)",
  INSUFFICIENT_DATA: "var(--neutral-verdict)",
  NOT_SUITABLE: "var(--bad)",
};

// Marker glyphs are drawn by google.maps, which needs real colour values —
// CSS custom properties don't resolve inside a canvas-rendered marker.
const VERDICT_HEX: Record<Verdict, string> = {
  SUITABLE: "#1f7a4d",
  SUITABLE_SUBJECT_TO_SURVEY: "#b5590c",
  CONDITIONAL: "#b5590c",
  INSUFFICIENT_DATA: "#64748b",
  NOT_SUITABLE: "#b3261e",
};
const DEFAULT_PIN_HEX = "#2f5f96";

const API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

// Zoom close enough that an individual rooftop fills a useful part of the
// frame — this is a roof-assessment product, not a navigation one.
const BUILDING_ZOOM = 19;
const MULTI_PIN_ZOOM = 11;

function pinIcon(color: string): google.maps.Symbol {
  return {
    path: "M 0,0 C -2,-20 -10,-22 -10,-30 A 10,10 0 1,1 10,-30 C 10,-22 2,-20 0,0 z",
    fillColor: color,
    fillOpacity: 1,
    strokeColor: "#ffffff",
    strokeWeight: 1.5,
    scale: 0.7,
  };
}

/** Keeps the viewport following `center` when the parent moves it
 *  (address search, geolocation) without fighting the user's own panning:
 *  it only recentres when the target actually changes. */
function ViewportSync({ center, zoom }: { center: { lat: number; lng: number } | null; zoom?: number }) {
  const map = useMap();
  const key = center ? `${center.lat.toFixed(6)},${center.lng.toFixed(6)}` : null;

  useEffect(() => {
    if (!map || !center) return;
    map.panTo(center);
    if (zoom != null) map.setZoom(zoom);
    // Deliberately keyed on the rounded coordinate string, not the object —
    // a new object identity every render would re-pan on each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key, zoom]);

  return null;
}

export function MapView({
  pins,
  height = 420,
  drawEnabled = false,
  interactive = false,
  onMove,
  center,
  solarPanels,
}: {
  pins: MapPinData[];
  height?: number;
  drawEnabled?: boolean;
  /** When true (and onMove is provided), tapping the map or dragging the pin repositions it. */
  interactive?: boolean;
  onMove?: (lat: number, lng: number) => void;
  /** Optional viewport override — lets a parent recentre after a search or
   *  a geolocation fix without having to place a pin first. */
  center?: { lat: number; lng: number } | null;
  /** Google's real per-panel layout, drawn over the satellite imagery.
   *  Omitted or empty renders nothing — never a placeholder array. */
  solarPanels?: SolarPanelPolygon[];
}) {
  const [dragPos, setDragPos] = useState<{ lat: number; lng: number } | null>(null);

  const focus = useMemo(() => {
    if (center) return center;
    if (pins.length === 1) return { lat: pins[0].lat, lng: pins[0].lng };
    if (pins.length > 1) {
      // Centroid of the set — good enough for a portfolio overview.
      const lat = pins.reduce((s, p) => s + p.lat, 0) / pins.length;
      const lng = pins.reduce((s, p) => s + p.lng, 0) / pins.length;
      return { lat, lng };
    }
    return null;
  }, [center, pins]);

  const zoom = pins.length > 1 ? MULTI_PIN_ZOOM : BUILDING_ZOOM;

  const handleMapClick = useCallback(
    (e: { detail: { latLng: { lat: number; lng: number } | null } }) => {
      if (!interactive || !onMove) return;
      const ll = e.detail.latLng;
      if (ll) onMove(ll.lat, ll.lng);
    },
    [interactive, onMove]
  );

  // Without a key the map cannot load at all. Say so plainly rather than
  // rendering an empty grey box the user can't act on.
  if (!API_KEY) {
    return (
      <div
        style={{ height }}
        className="flex flex-col items-center justify-center gap-1 rounded-[var(--radius-app)] border border-line bg-surface px-6 text-center text-sm text-ink-soft"
        role="alert"
      >
        <MapPin size={20} strokeWidth={1.75} aria-hidden="true" />
        <span>Map unavailable — NEXT_PUBLIC_GOOGLE_MAPS_API_KEY is not set.</span>
      </div>
    );
  }

  if (!focus) {
    return (
      <div
        style={{ height }}
        className="flex flex-col items-center justify-center gap-1 rounded-[var(--radius-app)] border border-line bg-surface px-6 text-center text-sm text-ink-soft"
      >
        <MapPin size={20} strokeWidth={1.75} aria-hidden="true" />
        <span>Search for an address or use your current location to place the map.</span>
      </div>
    );
  }

  return (
    <div
      className="relative overflow-hidden rounded-[var(--radius-app)] border border-line"
      style={{ height }}
    >
      <APIProvider apiKey={API_KEY}>
        <GoogleMap
          defaultCenter={focus}
          defaultZoom={zoom}
          mapTypeId="satellite"
          gestureHandling="greedy"
          disableDefaultUI={false}
          mapTypeControl={false}
          streetViewControl={false}
          fullscreenControl={false}
          onClick={handleMapClick}
          style={{ width: "100%", height: "100%" }}
        >
          <ViewportSync center={focus} zoom={zoom} />

          {pins.map((p) => {
            const isDraggablePin = interactive && !!onMove && pins.length === 1;
            const live = isDraggablePin && dragPos ? dragPos : { lat: p.lat, lng: p.lng };
            const hex = p.verdict ? VERDICT_HEX[p.verdict] : DEFAULT_PIN_HEX;
            return (
              <Marker
                key={p.id}
                position={live}
                title={p.verdict ? `${p.label} · ${VERDICT_LABEL[p.verdict]}` : p.label}
                icon={pinIcon(hex)}
                draggable={isDraggablePin}
                // Track locally while dragging so the marker follows the
                // cursor smoothly, then hand the final position upward.
                onDrag={(e) => {
                  const ll = e.latLng;
                  if (ll) setDragPos({ lat: ll.lat(), lng: ll.lng() });
                }}
                onDragEnd={(e) => {
                  const ll = e.latLng;
                  setDragPos(null);
                  if (ll && onMove) onMove(ll.lat(), ll.lng());
                }}
              />
            );
          })}

          {/* Google's real solar-panel layout, over the real imagery.
              Rendered only when panels actually came back — an absent
              layout shows the plain satellite view, never stand-in
              rectangles. */}
          {solarPanels && solarPanels.length > 0 && <SolarPanelOverlay panels={solarPanels} />}

          {/* Roof-polygon drawing hooks in here. The drawing library is
              available on this key (verified), and PUT /app/sites/{id}/boundary
              already accepts {points: [{lat,lng}...]} and versions it through
              SITE-05. Deliberately NOT stubbed with a fake polygon — an empty
              extension point is honest, a drawn-on rectangle is not. */}
        </GoogleMap>
      </APIProvider>

      {/* Anchored TOP, not bottom: Google's imagery attribution sits along
          the bottom edge and their Terms of Service require it to stay
          visible and unobscured. */}
      <div className="pointer-events-none absolute left-2 right-2 top-2 flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-line bg-paper/95 px-2.5 py-1.5 text-[11px] text-ink-soft">
        <span>
          {interactive && onMove
            ? "Drag the pin, or tap the map, to place it exactly on your roof."
            : `${pins.length} location${pins.length === 1 ? "" : "s"}`}
        </span>
        {drawEnabled && <span className="italic">Roof drawing coming soon.</span>}
      </div>
    </div>
  );
}

export const MAP_VERDICT_COLOR = VERDICT_COLOR;
