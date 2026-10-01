"use client";

// Draws Google's real solar-panel layout over the satellite imagery.
//
// Every rectangle here is one entry from the Solar API's solarPanels[],
// with corners computed server-side in a metre-based local projection
// (engine/panel_layout.py). Nothing is generated, evened out, or laid on
// a grid to look tidy: if Google returns no layout, this renders nothing.
//
// Panels are drawn as imperative google.maps.Polygon objects rather than
// as React components. A rooftop can carry 50+ panels, and one React
// element per panel means 50+ reconciliations on every pan and zoom; the
// Maps API redraws its own overlays on viewport changes for free.

import { useEffect, useRef } from "react";
import { useMap } from "@vis.gl/react-google-maps";

export interface SolarPanelPolygon {
  corners: { lat: number; lng: number }[];
  capacityWatts?: number | null;
  orientation: string;
  segmentIndex?: number | null;
  azimuthDegrees?: number | null;
  pitchDegrees?: number | null;
}

// Dark blue-black laminate with a light frame, at partial opacity so the
// roof stays readable underneath — the point is to show panels ON the
// customer's roof, not to hide the roof behind them.
const PANEL_FILL = "#101b3d";
const PANEL_FILL_OPACITY = 0.72;
const PANEL_STROKE = "#cfd6e4";
const PANEL_STROKE_WEIGHT = 1;
const PANEL_HOVER_FILL = "#1d3a86";

// Obstacles read as a warning, not as hardware: amber outline, light fill,
// so they are obviously "keep clear" rather than "installed".
const OBSTACLE_FILL = "#c2410c";
const OBSTACLE_FILL_OPACITY = 0.3;
const OBSTACLE_STROKE = "#fb923c";

// Restricted zones (setbacks + applied exclusions, Site.exclusions) are a
// DIFFERENT concept from a detected obstacle — this is the real geometry
// subtracted from the usable roof before packing ever ran, not a specific
// physical object. Deliberately a different color (red vs. the obstacles'
// amber) at lower opacity so the two don't read as the same thing.
const RESTRICTED_STROKE = "#dc2626";
const RESTRICTED_FILL = "#dc2626";
const RESTRICTED_FILL_OPACITY = 0.12;

// The roof footprint GEO-04 detected. Outline only, no fill — it exists to
// answer "which building do these panels belong to", not to compete with
// the imagery underneath.
// Brand-adjacent emerald, bright enough to stay legible against dark
// satellite imagery — matches the new clean-energy identity.
const ROOF_STROKE = "#3ddc97";

// Step 14 — each roof PLANE gets its own fill, colored by its REAL relative
// sunshine rank (sunniest -> most shaded), not an arbitrary per-index hue.
// A customer can read "the brighter section gets more sun" directly off
// the map instead of needing the legend to decode six unrelated colors.
const SUNSHINE_GRADIENT = ["#facc15", "#fb923c", "#f87171", "#a78bfa", "#64748b"];
const SEGMENT_FILL_OPACITY = 0.18;
const SEGMENT_STROKE_OPACITY = 0.6;

export interface RoofSegmentPolygon {
  segmentIndex: number;
  polygon: { lat: number; lng: number }[];
  pitchDeg?: number | null;
  azimuthDeg?: number | null;
  areaM2?: number | null;
  sunshineQuantiles?: number[];
}

function medianSunshine(segment: RoofSegmentPolygon): number | null {
  const q = segment.sunshineQuantiles;
  if (!q || q.length === 0) return null;
  return q[Math.floor(q.length / 2)];
}

/** Ranks segments sunniest-first (nulls last) and returns a color per
 *  segmentIndex from SUNSHINE_GRADIENT — real shading data driving the
 *  color choice, not the segment's arbitrary array position. */
function sunshineColorsByIndex(segments: RoofSegmentPolygon[]): Map<number, string> {
  const ranked = [...segments].sort((a, b) => {
    const ma = medianSunshine(a);
    const mb = medianSunshine(b);
    if (ma == null && mb == null) return 0;
    if (ma == null) return 1;
    if (mb == null) return -1;
    return mb - ma;
  });
  const colors = new Map<number, string>();
  ranked.forEach((segment, rank) => {
    const gradientIndex = ranked.length > 1
      ? Math.round((rank / (ranked.length - 1)) * (SUNSHINE_GRADIENT.length - 1))
      : 0;
    colors.set(segment.segmentIndex, SUNSHINE_GRADIENT[gradientIndex]);
  });
  return colors;
}

function describeSegment(segment: RoofSegmentPolygon): string {
  const bits: string[] = [`roof section ${segment.segmentIndex + 1}`];
  if (segment.azimuthDeg != null) bits.push(`facing ${Math.round(segment.azimuthDeg)}°`);
  if (segment.pitchDeg != null) bits.push(`${segment.pitchDeg.toFixed(1)}° pitch`);
  if (segment.areaM2 != null) bits.push(`${segment.areaM2.toFixed(0)} m²`);
  return bits.join(" · ");
}

function describe(panel: SolarPanelPolygon): string {
  const bits: string[] = [];
  if (panel.capacityWatts) bits.push(`${panel.capacityWatts} W`);
  bits.push(panel.orientation.toLowerCase());
  if (panel.azimuthDegrees != null) bits.push(`facing ${Math.round(panel.azimuthDegrees)}°`);
  if (panel.pitchDegrees != null) bits.push(`${panel.pitchDegrees.toFixed(1)}° pitch`);
  if (panel.segmentIndex != null) bits.push(`roof section ${panel.segmentIndex + 1}`);
  return bits.join(" · ");
}

export interface RoofObstaclePolygon {
  id: string;
  polygon: { lat: number; lng: number }[];
}

export interface LayerVisibility {
  panels: boolean;
  obstacles: boolean;
  restrictedZones: boolean;
  segments: boolean;
}

export function SolarPanelOverlay({
  panels,
  obstacles = [],
  restrictedZones = [],
  roofSegments = [],
  roofBoundary,
  visibility = { panels: true, obstacles: true, restrictedZones: true, segments: true },
}: {
  panels: SolarPanelPolygon[];
  /** OBS-04 obstacles applied to this roof. Empty renders nothing — an
   *  obstacle is never inferred here from imagery or elevation. */
  obstacles?: RoofObstaclePolygon[];
  /** Site.exclusions rings (setbacks + applied obstacles already
   *  subtracted from the usable area) — the real geometry the packer
   *  worked around, distinct from the discrete obstacle shapes above. */
  restrictedZones?: { lat: number; lng: number }[][];
  /** Each roof plane's own share of the usable roof (Step 14) — drawn as
   *  a distinctly-coloured light fill under the panels/obstacles. Empty
   *  when the roof has no Building Insights segment data. */
  roofSegments?: RoofSegmentPolygon[];
  /** The roof GEO-04 actually detected. Drawn as a bare outline so an
   *  apparent panel offset can be read for what it is: the panels sit on
   *  THIS footprint, and tall buildings shift between imagery captures. */
  roofBoundary?: { lat: number; lng: number }[];
  /** Per-layer show/hide — the roof boundary outline itself is always
   *  shown when present (it's the map's base orientation, not a togglable
   *  data layer). */
  visibility?: LayerVisibility;
}) {
  const map = useMap();
  const panelShapes = useRef<google.maps.Polygon[]>([]);
  const obstacleShapes = useRef<google.maps.Polygon[]>([]);
  const restrictedShapes = useRef<google.maps.Polygon[]>([]);
  const segmentShapes = useRef<google.maps.Polygon[]>([]);
  const roofShape = useRef<google.maps.Polygon | null>(null);
  const info = useRef<google.maps.InfoWindow | null>(null);

  useEffect(() => {
    if (
      !map ||
      (panels.length === 0 &&
        obstacles.length === 0 &&
        restrictedZones.length === 0 &&
        roofSegments.length === 0 &&
        !roofBoundary?.length)
    )
      return;

    const segmentColors = sunshineColorsByIndex(roofSegments);

    // Drawn UNDER everything else (lowest zIndex besides the roof
    // outline itself): this is background context for where the
    // obstacles/panels sit, not the subject.
    const newSegmentShapes = roofSegments.map((segment) => {
      const color = segmentColors.get(segment.segmentIndex) ?? SUNSHINE_GRADIENT[0];
      const shape = new google.maps.Polygon({
        paths: segment.polygon,
        strokeColor: color,
        strokeOpacity: SEGMENT_STROKE_OPACITY,
        strokeWeight: 1.5,
        fillColor: color,
        fillOpacity: SEGMENT_FILL_OPACITY,
        clickable: true,
        zIndex: 0.5,
        map,
      });
      shape.addListener("click", (event: google.maps.PolyMouseEvent) => {
        if (!event.latLng) return;
        info.current ??= new google.maps.InfoWindow();
        info.current.setContent(
          `<div style="font:12px system-ui;color:#1f2933;padding:1px 2px">${describeSegment(segment)}</div>`
        );
        info.current.setPosition(event.latLng);
        info.current.open({ map });
      });
      return shape;
    });

    const newRoofShape =
      roofBoundary && roofBoundary.length >= 3
        ? new google.maps.Polygon({
            paths: roofBoundary,
            strokeColor: ROOF_STROKE,
            strokeOpacity: 0.85,
            strokeWeight: 2,
            fillOpacity: 0,
            clickable: false,
            zIndex: 0,
            map,
          })
        : null;

    // Restricted zones (setbacks + applied exclusions) — a dashed red
    // outline, deliberately distinct from the obstacles' solid amber fill
    // below, since this is the real subtracted-geometry the packer worked
    // around, not a specific physical object.
    const newRestrictedShapes = restrictedZones.map(
      (ring) =>
        new google.maps.Polygon({
          paths: ring,
          strokeColor: RESTRICTED_STROKE,
          strokeOpacity: 0.9,
          strokeWeight: 1.5,
          fillColor: RESTRICTED_FILL,
          fillOpacity: RESTRICTED_FILL_OPACITY,
          clickable: false,
          zIndex: 0.8,
          map,
        })
    );

    // Drawn UNDER the panels (lower zIndex): where a panel sits beside a
    // water tank the panel is the subject, and an obstacle outline that
    // covered it would hide the thing the customer came to see.
    const newObstacleShapes = obstacles.map(
      (obstacle) =>
        new google.maps.Polygon({
          paths: obstacle.polygon,
          strokeColor: OBSTACLE_STROKE,
          strokeOpacity: 0.95,
          strokeWeight: 1.5,
          fillColor: OBSTACLE_FILL,
          fillOpacity: OBSTACLE_FILL_OPACITY,
          clickable: false,
          zIndex: 1,
          map,
        })
    );

    const newPanelShapes = panels.map((panel) => {
      const polygon = new google.maps.Polygon({
        paths: panel.corners,
        strokeColor: PANEL_STROKE,
        strokeOpacity: 0.9,
        strokeWeight: PANEL_STROKE_WEIGHT,
        fillColor: PANEL_FILL,
        fillOpacity: PANEL_FILL_OPACITY,
        clickable: true,
        zIndex: 2,
        map,
      });

      polygon.addListener("mouseover", () => polygon.setOptions({ fillColor: PANEL_HOVER_FILL }));
      polygon.addListener("mouseout", () => polygon.setOptions({ fillColor: PANEL_FILL }));
      polygon.addListener("click", (event: google.maps.PolyMouseEvent) => {
        if (!event.latLng) return;
        info.current ??= new google.maps.InfoWindow();
        info.current.setContent(
          `<div style="font:12px system-ui;color:#1f2933;padding:1px 2px">${describe(panel)}</div>`
        );
        info.current.setPosition(event.latLng);
        info.current.open({ map });
      });

      return polygon;
    });

    panelShapes.current = newPanelShapes;
    obstacleShapes.current = newObstacleShapes;
    restrictedShapes.current = newRestrictedShapes;
    segmentShapes.current = newSegmentShapes;
    roofShape.current = newRoofShape;

    return () => {
      info.current?.close();
      const all = [
        ...newPanelShapes,
        ...newObstacleShapes,
        ...newRestrictedShapes,
        ...newSegmentShapes,
        ...(newRoofShape ? [newRoofShape] : []),
      ];
      all.forEach((p) => {
        google.maps.event.clearInstanceListeners(p);
        p.setMap(null);
      });
      panelShapes.current = [];
      obstacleShapes.current = [];
      restrictedShapes.current = [];
      segmentShapes.current = [];
      roofShape.current = null;
    };
  }, [map, panels, obstacles, restrictedZones, roofSegments, roofBoundary]);

  // Toggling visibility reuses the existing polygons rather than
  // destroying and rebuilding 50+ of them — independent per layer, so a
  // customer can isolate just the panels or just the restricted zones.
  useEffect(() => {
    if (!map) return;
    panelShapes.current.forEach((p) => p.setMap(visibility.panels ? map : null));
    obstacleShapes.current.forEach((p) => p.setMap(visibility.obstacles ? map : null));
    restrictedShapes.current.forEach((p) => p.setMap(visibility.restrictedZones ? map : null));
    segmentShapes.current.forEach((p) => p.setMap(visibility.segments ? map : null));
    if (!visibility.panels && !visibility.obstacles && !visibility.segments) info.current?.close();
  }, [map, visibility]);

  return null;
}
