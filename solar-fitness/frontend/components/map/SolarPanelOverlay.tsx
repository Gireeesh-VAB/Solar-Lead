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

function describe(panel: SolarPanelPolygon): string {
  const bits: string[] = [];
  if (panel.capacityWatts) bits.push(`${panel.capacityWatts} W`);
  bits.push(panel.orientation.toLowerCase());
  if (panel.azimuthDegrees != null) bits.push(`facing ${Math.round(panel.azimuthDegrees)}°`);
  if (panel.pitchDegrees != null) bits.push(`${panel.pitchDegrees.toFixed(1)}° pitch`);
  if (panel.segmentIndex != null) bits.push(`roof section ${panel.segmentIndex + 1}`);
  return bits.join(" · ");
}

export function SolarPanelOverlay({
  panels,
  visible = true,
}: {
  panels: SolarPanelPolygon[];
  visible?: boolean;
}) {
  const map = useMap();
  const drawn = useRef<google.maps.Polygon[]>([]);
  const info = useRef<google.maps.InfoWindow | null>(null);

  useEffect(() => {
    if (!map || panels.length === 0) return;

    const polygons = panels.map((panel) => {
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

    drawn.current = polygons;
    return () => {
      info.current?.close();
      polygons.forEach((p) => {
        google.maps.event.clearInstanceListeners(p);
        p.setMap(null);
      });
      drawn.current = [];
    };
  }, [map, panels]);

  // Toggling visibility reuses the existing polygons rather than
  // destroying and rebuilding 50+ of them.
  useEffect(() => {
    if (!map) return;
    drawn.current.forEach((p) => p.setMap(visible ? map : null));
    if (!visible) info.current?.close();
  }, [map, visible]);

  return null;
}
