"use client";

import { type ReactNode, useMemo, useRef, useState } from "react";
import { APIProvider, AdvancedMarker, Map, Pin, type MapMouseEvent } from "@vis.gl/react-google-maps";
import { MapPin } from "lucide-react";
import type { Verdict } from "@/lib/types";
import { VERDICT_LABEL, cn } from "@/lib/utils";

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

const VERDICT_HEX: Record<Verdict, string> = {
  SUITABLE: "#16a34a",
  SUITABLE_SUBJECT_TO_SURVEY: "#d97706",
  CONDITIONAL: "#d97706",
  INSUFFICIENT_DATA: "#6b7280",
  NOT_SUITABLE: "#dc2626",
};

const MAPS_API_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
const HAS_MAPS_KEY = !!MAPS_API_KEY;

// AdvancedMarkerElement requires the map to have a Map ID (vector or
// raster). We don't have a real one provisioned in Google Cloud Console
// for this project, so we use Google's own "DEMO_MAP_ID" — documented and
// intended for exactly this (development/testing without a configured
// Map ID). Styling then falls back to the default Google style.
const MAP_ID = "DEMO_MAP_ID";

const DEFAULT_CENTER = { lat: 20.5937, lng: 78.9629 }; // India, used when there are no pins yet
const DEFAULT_ZOOM = 5;
const SINGLE_PIN_ZOOM = 15;

/** Wraps children in the Google Maps API context. Use this at the top of a
 * page that needs both MapView (with `standalone={false}`) and other
 * Maps-powered features (e.g. `useMapsLibrary("geocoding")`) sharing the
 * same loaded API — nesting two APIProviders is not supported. Pages that
 * only need the map itself can skip this and use MapView's default
 * (`standalone={true}`), which wraps itself. */
export function MapsProvider({ children }: { children: ReactNode }) {
  if (!HAS_MAPS_KEY) return <>{children}</>;
  return <APIProvider apiKey={MAPS_API_KEY}>{children}</APIProvider>;
}

function boundsCenterAndZoom(pins: MapPinData[]): { center: google.maps.LatLngLiteral; zoom: number } {
  if (pins.length === 0) return { center: DEFAULT_CENTER, zoom: DEFAULT_ZOOM };
  if (pins.length === 1) return { center: { lat: pins[0].lat, lng: pins[0].lng }, zoom: SINGLE_PIN_ZOOM };
  const lats = pins.map((p) => p.lat);
  const lngs = pins.map((p) => p.lng);
  return {
    center: {
      lat: (Math.min(...lats) + Math.max(...lats)) / 2,
      lng: (Math.min(...lngs) + Math.max(...lngs)) / 2,
    },
    zoom: 12,
  };
}

function LiveMap({
  pins,
  height,
  interactive,
  onMove,
}: {
  pins: MapPinData[];
  height: number;
  interactive: boolean;
  onMove?: (lat: number, lng: number) => void;
}) {
  const { center, zoom } = useMemo(() => boundsCenterAndZoom(pins), [pins]);

  const handleClick = (event: MapMouseEvent) => {
    if (!interactive || !onMove || !event.detail.latLng) return;
    onMove(event.detail.latLng.lat, event.detail.latLng.lng);
  };

  return (
    <div
      style={{ height }}
      className={cn("overflow-hidden rounded-[var(--radius-app)] border border-line", interactive && "cursor-crosshair")}
    >
      <Map
        defaultCenter={center}
        defaultZoom={zoom}
        center={pins.length === 1 ? center : undefined}
        gestureHandling="greedy"
        disableDefaultUI={false}
        mapId={MAP_ID}
        onClick={handleClick}
        style={{ width: "100%", height: "100%" }}
      >
        {pins.map((p) => (
          <AdvancedMarker
            key={p.id}
            position={{ lat: p.lat, lng: p.lng }}
            title={p.label}
            draggable={interactive}
            onDragEnd={(event) => {
              const pos = event.latLng;
              if (pos && onMove) onMove(pos.lat(), pos.lng());
            }}
          >
            <Pin
              background={p.verdict ? VERDICT_HEX[p.verdict] : "#2563eb"}
              borderColor="#ffffff"
              glyphColor="#ffffff"
            />
          </AdvancedMarker>
        ))}
      </Map>
    </div>
  );
}

// Deterministic SVG "map preview" fallback for when no Google Maps API key
// is configured (NEXT_PUBLIC_GOOGLE_MAPS_API_KEY) — keeps the page usable
// instead of crashing or showing a blank box.
function FallbackMap({
  pins,
  height,
  drawEnabled,
  interactive,
  onMove,
}: {
  pins: MapPinData[];
  height: number;
  drawEnabled: boolean;
  interactive: boolean;
  onMove?: (lat: number, lng: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);

  const bounds = useMemo(() => {
    if (pins.length === 0) return { minLat: 0, maxLat: 1, minLng: 0, maxLng: 1 };
    const lats = pins.map((p) => p.lat);
    const lngs = pins.map((p) => p.lng);
    return {
      minLat: Math.min(...lats) - 0.05,
      maxLat: Math.max(...lats) + 0.05,
      minLng: Math.min(...lngs) - 0.05,
      maxLng: Math.max(...lngs) + 0.05,
    };
  }, [pins]);

  const project = (lat: number, lng: number) => {
    const x = ((lng - bounds.minLng) / (bounds.maxLng - bounds.minLng || 1)) * 100;
    const y = 100 - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat || 1)) * 100;
    return { x, y };
  };

  const toLatLng = (clientX: number, clientY: number) => {
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    const xPct = ((clientX - rect.left) / rect.width) * 100;
    const yPct = ((clientY - rect.top) / rect.height) * 100;
    const lng = bounds.minLng + (xPct / 100) * (bounds.maxLng - bounds.minLng);
    const lat = bounds.minLat + ((100 - yPct) / 100) * (bounds.maxLat - bounds.minLat);
    return { lat, lng };
  };

  const handlePoint = (clientX: number, clientY: number) => {
    if (!interactive || !onMove) return;
    const result = toLatLng(clientX, clientY);
    if (result) onMove(result.lat, result.lng);
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative overflow-hidden rounded-[var(--radius-app)] border border-line",
        interactive && "cursor-crosshair"
      )}
      style={{ height, background: "var(--surface)" }}
      role="img"
      aria-label={interactive ? "Map — tap or drag to place your pin" : `Map preview showing ${pins.length} site pins`}
      onClick={(e) => {
        if (dragging) return;
        handlePoint(e.clientX, e.clientY);
      }}
      onPointerMove={(e) => {
        if (!dragging) return;
        handlePoint(e.clientX, e.clientY);
      }}
      onPointerUp={() => setDragging(false)}
      onPointerLeave={() => setDragging(false)}
    >
      <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        {Array.from({ length: 11 }).map((_, i) => (
          <line key={`v${i}`} x1={i * 10} y1={0} x2={i * 10} y2={100} stroke="var(--line)" strokeWidth={0.15} />
        ))}
        {Array.from({ length: 11 }).map((_, i) => (
          <line key={`h${i}`} x1={0} y1={i * 10} x2={100} y2={i * 10} stroke="var(--line)" strokeWidth={0.15} />
        ))}
      </svg>
      <div className="absolute inset-0">
        {pins.map((p) => {
          const { x, y } = project(p.lat, p.lng);
          const color = p.verdict ? VERDICT_COLOR[p.verdict] : "var(--blue)";
          return (
            <div
              key={p.id}
              className={cn("group absolute -translate-x-1/2 -translate-y-full", interactive && "cursor-grab active:cursor-grabbing")}
              style={{ left: `${x}%`, top: `${y}%` }}
              onPointerDown={
                interactive
                  ? (e) => {
                      e.stopPropagation();
                      setDragging(true);
                    }
                  : undefined
              }
            >
              <MapPin size={20} strokeWidth={1.75} color={color} fill={color} fillOpacity={0.15} aria-hidden="true" />
              <div
                className="pointer-events-none absolute left-1/2 top-full z-10 hidden -translate-x-1/2 whitespace-nowrap rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1 text-[11px] text-ink shadow-[var(--shadow-float)] group-hover:block"
              >
                {p.label}
                {p.verdict && <span className="ml-1 text-ink-soft">· {VERDICT_LABEL[p.verdict]}</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between gap-2 rounded-[var(--radius-app)] border border-line bg-paper/95 px-2.5 py-1.5 text-[11px] text-ink-soft">
        <span>
          {interactive
            ? "Tap the map or drag the pin to set your location. Connect a Google Maps API key to enable live imagery."
            : "Map preview — connect Google Maps API key to enable live imagery."}
        </span>
        {drawEnabled && <span className="italic">Drawing tools disabled in preview mode.</span>}
      </div>
    </div>
  );
}

export function MapView({
  pins,
  height = 420,
  drawEnabled = false,
  interactive = false,
  onMove,
  standalone = true,
}: {
  pins: MapPinData[];
  height?: number;
  drawEnabled?: boolean;
  /** When true (and onMove is provided), tapping/dragging the map repositions the pin. */
  interactive?: boolean;
  onMove?: (lat: number, lng: number) => void;
  /** Set to false when the caller already wraps the page in `<MapsProvider>`
   * (e.g. to also use `useMapsLibrary` for geocoding/search) — avoids
   * nesting a second, unsupported APIProvider. */
  standalone?: boolean;
}) {
  if (!HAS_MAPS_KEY) {
    return <FallbackMap pins={pins} height={height} drawEnabled={drawEnabled} interactive={interactive} onMove={onMove} />;
  }

  const map = <LiveMap pins={pins} height={height} interactive={interactive} onMove={onMove} />;
  return standalone ? <MapsProvider>{map}</MapsProvider> : map;
}
