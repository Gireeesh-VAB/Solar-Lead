"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  APIProvider,
  Map as GoogleMap,
  Marker,
  useMap,
} from "@vis.gl/react-google-maps";
import { MapPin } from "lucide-react";
import { RoofBoundaryEditor, type LatLngPoint } from "./RoofBoundaryEditor";
import {
  SolarPanelOverlay,
  type LayerVisibility,
  type RoofObstaclePolygon,
  type RoofSegmentPolygon,
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
  SUITABLE: "#1e7a5f",
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

/** Steps `map`'s zoom from `from` to `to` one level at a time, spaced
 *  `durationMs` apart in total — the Maps JS API has no native smooth-
 *  zoom transition (setZoom() jumps instantly), so this fakes one by
 *  animating through the intermediate integer levels. Returns a cleanup
 *  function that stops the sequence if the target changes mid-flight
 *  (a fast re-pin during the animation must not leave two sequences
 *  fighting each other). No-op (immediate jump) when `to <= from` —
 *  never animates a zoom-OUT, only zooming in reads as "homing in on
 *  the roof". */
function animateZoomTo(map: google.maps.Map, from: number, to: number, durationMs = 900): () => void {
  if (to <= from) {
    map.setZoom(to);
    return () => {};
  }
  const steps = to - from;
  const stepDelayMs = durationMs / steps;
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const tick = (level: number) => {
    if (cancelled) return;
    map.setZoom(level);
    if (level < to) timer = setTimeout(() => tick(level + 1), stepDelayMs);
  };
  tick(from + 1);

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}

/** Zooms to the highest level Google actually has imagery for at `point`,
 *  animating the approach rather than jumping straight there — Step 15's
 *  "camera smoothly zooms to selected building", not an instant cut.
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
    let stopAnimation: (() => void) | null = null;

    new google.maps.MaxZoomService()
      .getMaxZoomAtLatLng(point)
      .then((result) => {
        if (cancelled || result.status !== google.maps.MaxZoomStatus.OK) return;
        const best = Math.min(result.zoom, MAX_USEFUL_ZOOM);
        // Never zoom OUT from the building framing — only sharpen it.
        const current = map.getZoom() ?? 0;
        if (best > current) stopAnimation = animateZoomTo(map, current, best);
      })
      .catch(() => {
        // No imagery-depth answer available; the existing zoom stands.
      });

    return () => {
      cancelled = true;
      stopAnimation?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);

  return null;
}

/** Keeps the viewport following `center` when the parent moves it
 *  (address search, geolocation, a dragged/tapped pin) without fighting
 *  the user's own panning: it only recentres when the target actually
 *  changes.
 *
 *  `zoom` is deliberately NOT applied here for the single/no-pin case
 *  (see the `pins.length <= 1` check where this is mounted below) —
 *  ZoomToBestImagery owns that decision so it can animate smoothly and
 *  never zoom out. This component using `map.setZoom()` (an instant
 *  jump) on every pin adjustment used to fight it: each drag/tap first
 *  hard-reset the zoom back down to BUILDING_ZOOM, THEN
 *  ZoomToBestImagery tried to animate back up — visible as "the exact
 *  point doesn't zoom in properly" while adjusting the pin, because the
 *  reset undid whatever zoom level the customer had already reached.
 *  Multi-pin portfolio views have no ZoomToBestImagery running at all,
 *  so they still pass `zoom` through here to get one. */
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
  restrictedZones,
  roofSegments,
  roofBoundary,
  layerVisibility,
  editableBoundary,
  onBoundaryChange,
  editorVersion,
  addPointSignal,
  draggableCursor,
  disableDoubleClickZoom,
  draggable,
  hint,
  children,
}: {
  pins: MapPinData[];
  /** A number is a pixel height (the historical default); a string
   *  (e.g. "100%") lets a full-screen wrapper (StartCheckWizard) size
   *  the map edge-to-edge without MapView needing its own viewport math. */
  height?: number | string;
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
  /** Site.exclusions rings — setbacks + applied obstacles already
   *  subtracted from the usable area. Same rule: empty draws nothing. */
  restrictedZones?: { lat: number; lng: number }[][];
  /** Each roof plane's own polygon (Step 14), drawn as a distinctly
   *  coloured light fill under the panels/obstacles. Same rule: empty
   *  draws nothing. */
  roofSegments?: RoofSegmentPolygon[];
  /** The detected roof footprint, outlined. */
  roofBoundary?: { lat: number; lng: number }[];
  /** Per-layer show/hide for the overlay above — omit to show everything. */
  layerVisibility?: LayerVisibility;
  /** Turns the map into a roof-tracing surface, starting from this shape.
   *  Supplying it replaces the read-only outline with an editable one. */
  editableBoundary?: LatLngPoint[];
  onBoundaryChange?: (points: LatLngPoint[]) => void;
  /** Bump to discard edits and restart from `editableBoundary`. */
  editorVersion?: number;
  /** Bump to insert a new corner at the midpoint of the shape's longest
   *  edge — the "Add Point" button's signal to RoofBoundaryEditor. */
  addPointSignal?: number;
  /** Native MapOptions.draggableCursor pass-through — e.g. "crosshair"
   *  while a click-to-place tool is active, so the pointer itself signals
   *  "click to place/draw" over the satellite imagery. */
  draggableCursor?: string;
  /** Native MapOptions.disableDoubleClickZoom pass-through — for a tool
   *  that places a point per click, where two clicks landing inside
   *  Google's own double-click window would otherwise zoom the map
   *  instead of (or as well as) registering the second point. */
  disableDoubleClickZoom?: boolean;
  /** Native MapOptions.draggable pass-through, default true. Set false
   *  while a click-to-place tool is active: with the default
   *  gestureHandling="greedy", a click with even a couple of pixels of
   *  movement — routine on a trackpad — reads as a pan, not a click, so
   *  the map slides instead of placing a point. Disabling drag removes
   *  that ambiguity entirely; the map still zooms via scroll/pinch/the
   *  on-screen controls, just doesn't pan from a click-drag. */
  draggable?: boolean;
  /** Overrides the caption in the top strip. `interactive` maps' default
   *  wording is about placing the location pin; a screen that reuses the
   *  same tap-to-place plumbing for something else (marking rooftop
   *  obstacles) needs to say what the tap will actually do. */
  hint?: string;
  /** Extra overlays rendered inside the live <GoogleMap>, alongside the
   *  built-in ones above — e.g. CropRectangleSelector/
   *  FreehandPolygonSelector, which (like RoofBoundaryEditor) resolve
   *  their map instance via useMap() and so must be mounted inside the
   *  same GoogleMap tree, not merely under APIProvider. */
  children?: ReactNode;
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
          draggableCursor={draggableCursor}
          disableDoubleClickZoom={disableDoubleClickZoom}
          draggable={draggable}
          style={{ width: "100%", height: "100%" }}
        >
          {/* Single/no-pin screens: ZoomToBestImagery owns zoom (smooth,
              never out) — ViewportSync only pans. Multi-pin portfolio
              views have no ZoomToBestImagery, so they get a fixed zoom
              here instead; a portfolio should stay zoomed out. */}
          <ViewportSync center={focus} zoom={pins.length > 1 ? zoom : undefined} />
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
          {/* Tracing mode. The read-only outline is suppressed while
              editing — two outlines of the same roof, one draggable and
              one not, is only confusing. */}
          {editableBoundary && onBoundaryChange && editableBoundary.length >= 3 && (
            <RoofBoundaryEditor
              initial={editableBoundary}
              onChange={onBoundaryChange}
              version={editorVersion}
              addPointSignal={addPointSignal}
            />
          )}

          {!editableBoundary &&
            ((solarPanels?.length ?? 0) > 0 ||
            (roofObstacles?.length ?? 0) > 0 ||
            (restrictedZones?.length ?? 0) > 0 ||
            (roofSegments?.length ?? 0) > 0 ||
            (roofBoundary?.length ?? 0) > 0) && (
            <SolarPanelOverlay
              panels={solarPanels ?? []}
              obstacles={roofObstacles ?? []}
              restrictedZones={restrictedZones ?? []}
              roofSegments={roofSegments ?? []}
              roofBoundary={roofBoundary}
              visibility={layerVisibility}
            />
          )}

          {/* CropRectangleSelector/FreehandPolygonSelector (StartCheckWizard's
              "Select Building" step) mount here — the extension point the
              comment this replaced was left for. */}
          {children}
        </GoogleMap>
      </APIProvider>

      {/* Anchored TOP, not bottom: Google's imagery attribution sits along
          the bottom edge and their Terms of Service require it to stay
          visible and unobscured. */}
      <div className="pointer-events-none absolute left-2 right-2 top-2 flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-line bg-paper/95 px-2.5 py-1.5 text-[11px] text-ink-soft">
        <span>
          {hint ??
            (interactive && onMove
              ? "Drag the pin, or tap the map, to place it exactly on your roof."
              : `${pins.length} location${pins.length === 1 ? "" : "s"}`)}
        </span>
        {drawEnabled && <span className="italic">Roof drawing coming soon.</span>}
      </div>
    </div>
  );
}

export const MAP_VERDICT_COLOR = VERDICT_COLOR;
