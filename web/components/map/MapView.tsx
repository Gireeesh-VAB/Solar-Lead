"use client";

import { useMemo, useRef, useState } from "react";
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

const HAS_MAPS_KEY = !!process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;

// Google Maps key is not provisioned in this environment. HAS_MAPS_KEY stays
// false, so this component renders a deterministic SVG "map preview" instead
// of crashing or showing a blank box. When a key is added to .env.local,
// swap in @vis.gl/react-google-maps here (dynamically imported) — the pin
// data contract (MapPinData) stays the same either way.
export function MapView({
  pins,
  height = 420,
  drawEnabled = false,
  interactive = false,
  onMove,
}: {
  pins: MapPinData[];
  height?: number;
  drawEnabled?: boolean;
  /** When true (and onMove is provided), tapping/dragging the map repositions the pin. */
  interactive?: boolean;
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

  if (HAS_MAPS_KEY) {
    // Real Google Maps integration point (not reached without an API key).
    return (
      <div style={{ height }} className="flex items-center justify-center rounded-[var(--radius-app)] border border-line bg-surface text-sm text-ink-soft">
        Live Google Maps would render here (@vis.gl/react-google-maps).
      </div>
    );
  }

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
