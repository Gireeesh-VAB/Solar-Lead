"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  APIProvider,
  Map as GoogleMap,
  Marker,
  useMap,
} from "@vis.gl/react-google-maps";
import { MapPin } from "lucide-react";
import {
  SolarPanelOverlay,
  type RoofObstaclePolygon,
  type SolarPanelPolygon,
} from "./SolarPanelOverlay";
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
//
// A floor, not the final value: ZoomToBestImagery below asks Google what
// the highest zoom with REAL satellite imagery is at this exact point and
// goes there instead. Past that ceiling Google upscales its own tiles, so
// zooming further only makes the roof blurrier.
const BUILDING_ZOOM = 20;

// Even where Google has more, this is as close as a rooftop needs; beyond
// it the roof overflows the frame and the surrounding context is lost.
const MAX_USEFUL_ZOOM = 21;
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
/** Zooms to the highest level Google actually has imagery for at `point`.
 *
 *  Satellite coverage depth varies street by street. A fixed zoom either
 *  wastes real resolution where Google has it, or pushes past the tiles
 *  it holds and shows an upscaled blur — which is exactly what a customer
 *  trying to recognise their own roof cannot afford.
 *
 *  MaxZoomService is part of Maps JavaScript, already loaded for the map
 *  itself, so this needs no extra key permission. If it fails the map
 *  simply keeps the zoom it had. */
function ZoomToBestImagery({ point }: { point: { lat: number; lng: number } | null }) {
  const map = useMap();
  const key = point ? `${point.lat.toFixed(6)},${point.lng.toFixed(6)}` : null;

  useEffect(() => {
    if (!map || !point || !google?.maps?.MaxZoomService) return;
    let cancelled = false;

    new google.maps.MaxZoomService()
      .getMaxZoomAtLatLng(point)
      .then((result) => {
        if (cancelled || result.status !== google.maps.MaxZoomStatus.OK) return;
        const best = Math.min(result.zoom, MAX_USEFUL_ZOOM);
        // Never zoom OUT from the building framing — only sharpen it.
        if (best > (map.getZoom() ?? 0)) map.setZoom(best);
      })
      .catch(() => {
        // No imagery-depth answer available; the existing zoom stands.
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);

  return null;
}

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
  roofObstacles,
  roofBoundary,
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
  /** OBS-04 obstacles applied to this roof. Same rule: empty draws nothing. */
  roofObstacles?: RoofObstaclePolygon[];
  /** The detected roof footprint, outlined. */
  roofBoundary?: { lat: number; lng: number }[];
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
          {/* Only for a single rooftop — a portfolio of pins is a
              different job and should stay zoomed out. */}
          {pins.length <= 1 && <ZoomToBestImagery point={focus} />}

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
          {((solarPanels?.length ?? 0) > 0 ||
            (roofObstacles?.length ?? 0) > 0 ||
            (roofBoundary?.length ?? 0) > 0) && (
            <SolarPanelOverlay
              panels={solarPanels ?? []}
              obstacles={roofObstacles ?? []}
              roofBoundary={roofBoundary}
            />
          )}

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
