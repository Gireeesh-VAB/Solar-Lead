"use client";

// Lets someone draw an outline FREEHAND on the satellite photo: press, drag
// round the thing, lift. Works with a mouse, a finger or a pen (pointer
// events), and the line follows the finger as it goes.
//
// While `active`, a transparent layer sits over the map and takes the
// pointer, so a drag draws instead of panning the map (turn `active` off to
// move or zoom the map again). Each point is turned into a lat/lng through
// the map's own projection, so the outline lands exactly where it was drawn
// whatever the zoom. The finished stroke is cleaned up by
// lib/geo/freehand.ts into a handful of corners that never cross, and handed
// to `onComplete` - the caller then lets the customer fine-tune the corners
// with RoofBoundaryEditor.
//
// Same "plain Google Maps object, no extra library" approach as
// RoofBoundaryEditor.

import { useEffect, useRef, useState } from "react";
import { useMap } from "@vis.gl/react-google-maps";
import { strokeToOutline, type Pt } from "@/lib/geo/freehand";

export interface FreehandPoint {
  lat: number;
  lng: number;
}

export function FreehandDrawLayer({
  active,
  onComplete,
  onReject,
  color = "#2563eb",
}: {
  /** Drawing is on: a drag draws. Off: the map pans and zooms as usual. */
  active: boolean;
  /** The finished outline: 3+ corners, closed implicitly, never crossing itself. */
  onComplete: (outline: FreehandPoint[]) => void;
  /** The stroke was not a drawing (a tap, a speck, a straight line). Says what to do. */
  onReject?: (message: string) => void;
  /** Colour of the line while drawing. */
  color?: string;
}) {
  const map = useMap();

  // Callbacks live in refs so the effect below (which owns a half-drawn
  // stroke) does not restart every time the parent re-renders.
  const complete = useRef(onComplete);
  const reject = useRef(onReject);
  useEffect(() => {
    complete.current = onComplete;
    reject.current = onReject;
  }, [onComplete, onReject]);

  // pixel -> lat/lng needs the map's projection, which only exists once an
  // OverlayView on the map has been drawn for the first time.
  const overlay = useRef<google.maps.OverlayView | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!map) return;
    const view = new google.maps.OverlayView();
    view.onAdd = () => {};
    view.onRemove = () => {};
    view.draw = () => setReady(true);
    view.setMap(map);
    overlay.current = view;
    return () => {
      view.setMap(null);
      overlay.current = null;
      setReady(false);
    };
  }, [map]);

  useEffect(() => {
    if (!map || !active || !ready) return;
    const container = map.getDiv();
    if (getComputedStyle(container).position === "static") container.style.position = "relative";

    const layer = document.createElement("div");
    Object.assign(layer.style, {
      position: "absolute",
      inset: "0",
      zIndex: "10",
      cursor: "crosshair",
      touchAction: "none", // a finger drags a line, it does not scroll the page or pan the map
      background: "transparent",
    });
    container.appendChild(layer);

    let stroke: Pt[] | null = null;
    let line: google.maps.Polyline | null = null;

    const toLatLng = (p: Pt): google.maps.LatLng | null =>
      overlay.current?.getProjection()?.fromContainerPixelToLatLng(new google.maps.Point(p.x, p.y)) ?? null;
    const local = (e: PointerEvent): Pt => {
      const box = container.getBoundingClientRect();
      return { x: e.clientX - box.left, y: e.clientY - box.top };
    };
    const clearLine = () => {
      line?.setMap(null);
      line = null;
    };

    const down = (e: PointerEvent) => {
      if (e.pointerType === "mouse" && e.button !== 0) return;
      e.preventDefault();
      layer.setPointerCapture(e.pointerId);
      const start = local(e);
      stroke = [start];
      clearLine();
      line = new google.maps.Polyline({ map, strokeColor: color, strokeWeight: 3, clickable: false, zIndex: 20 });
      const ll = toLatLng(start);
      if (ll) line.getPath().push(ll);
    };

    const move = (e: PointerEvent) => {
      if (!stroke) return;
      const p = local(e);
      const last = stroke[stroke.length - 1];
      if (Math.hypot(p.x - last.x, p.y - last.y) < 2) return; // ignore jitter
      stroke.push(p);
      const ll = toLatLng(p);
      if (ll) line?.getPath().push(ll);
    };

    const finish = (e: PointerEvent) => {
      if (!stroke) return;
      const raw = stroke;
      stroke = null;
      clearLine();
      if (layer.hasPointerCapture(e.pointerId)) layer.releasePointerCapture(e.pointerId);
      const outline = strokeToOutline(raw);
      const corners = outline?.map(toLatLng) ?? [];
      if (!outline || corners.some((c) => c === null)) {
        reject.current?.("That was too small to be an outline. Press, drag all the way round the obstacle, then lift.");
        return;
      }
      complete.current((corners as google.maps.LatLng[]).map((c) => ({ lat: c.lat(), lng: c.lng() })));
    };

    const cancel = () => {
      stroke = null;
      clearLine();
    };

    layer.addEventListener("pointerdown", down);
    layer.addEventListener("pointermove", move);
    layer.addEventListener("pointerup", finish);
    layer.addEventListener("pointercancel", cancel);

    return () => {
      layer.removeEventListener("pointerdown", down);
      layer.removeEventListener("pointermove", move);
      layer.removeEventListener("pointerup", finish);
      layer.removeEventListener("pointercancel", cancel);
      clearLine();
      layer.remove();
    };
  }, [map, active, ready, color]);

  return null;
}
