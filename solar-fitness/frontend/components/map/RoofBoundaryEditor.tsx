"use client";

// Lets someone correct the roof outline on the satellite photo.
//
// GEO-04 gives a 4-corner RECTANGLE around the building, never its
// outline. On an L-shaped or irregular roof that is not the roof, and
// everything downstream — usable area, capacity, panel placement —
// inherits the error.
//
// This starts FROM that rectangle rather than a blank map, because
// correcting four corners is a far smaller job than tracing from
// scratch, and the rectangle is already roughly in the right place.
//
// Built on google.maps.Polygon's own editable mode rather than the
// Drawing library: it gives vertex handles AND midpoint handles for
// free, and dragging a midpoint is exactly how a rectangle becomes an
// L — which is the shape this whole feature exists for. No extra
// library to load, and nothing to keep in sync with the map.

import { useEffect, useRef } from "react";
import { useMap } from "@vis.gl/react-google-maps";

export interface LatLngPoint {
  lat: number;
  lng: number;
}

const STROKE = "#22d3ee";
const FILL = "#22d3ee";

export function RoofBoundaryEditor({
  initial,
  onChange,
  version = 0,
}: {
  /** Starting shape — normally GEO-04's approximate rectangle. */
  initial: LatLngPoint[];
  /** Fires on every edit with the current ring. */
  onChange: (points: LatLngPoint[]) => void;
  /** Bump to discard edits and rebuild from `initial` (the Reset button). */
  version?: number;
}) {
  const map = useMap();
  const polygon = useRef<google.maps.Polygon | null>(null);
  // Kept in a ref so the effect below does not re-run — and therefore
  // does not destroy the polygon the user is mid-drag on — every time the
  // parent re-renders with a new callback identity. Synced in its own
  // effect rather than during render, which React forbids.
  const emit = useRef(onChange);
  useEffect(() => {
    emit.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!map || initial.length < 3) return;

    const shape = new google.maps.Polygon({
      paths: initial,
      strokeColor: STROKE,
      strokeOpacity: 0.95,
      strokeWeight: 2,
      fillColor: FILL,
      fillOpacity: 0.12,
      editable: true,
      draggable: true,
      zIndex: 5,
      map,
    });
    polygon.current = shape;

    const read = () =>
      shape
        .getPath()
        .getArray()
        .map((p) => ({ lat: p.lat(), lng: p.lng() }));

    const publish = () => emit.current(read());
    const path = shape.getPath();
    // insert_at fires when a midpoint handle is dragged out into a new
    // corner — the move that turns a rectangle into an L.
    const listeners = [
      path.addListener("set_at", publish),
      path.addListener("insert_at", publish),
      path.addListener("remove_at", publish),
      shape.addListener("dragend", publish),
      // Right-click a vertex to delete it. Google gives the index on the
      // event; guarded at 3 because fewer than three points is not an area.
      shape.addListener("rightclick", (event: google.maps.PolyMouseEvent) => {
        if (event.vertex === undefined || path.getLength() <= 3) return;
        path.removeAt(event.vertex);
      }),
    ];

    publish();

    return () => {
      listeners.forEach((l) => l.remove());
      google.maps.event.clearInstanceListeners(shape);
      shape.setMap(null);
      polygon.current = null;
    };
    // `initial` is intentionally not a dependency: it is the STARTING
    // shape, and rebuilding on every parent render would wipe the user's
    // work mid-edit. `version` is the explicit "start again" signal.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, version]);

  return null;
}
