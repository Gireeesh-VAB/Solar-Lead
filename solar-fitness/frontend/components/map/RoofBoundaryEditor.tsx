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
import { simplifyBoundary } from "@/lib/geo/simplify";

export interface LatLngPoint {
  lat: number;
  lng: number;
}

// Brand emerald — matches --brand in app/globals.css. Canvas/Maps drawing
// needs a real color value, CSS custom properties don't resolve here.
const STROKE = "#1e7a5f";
const FILL = "#1e7a5f";

export function RoofBoundaryEditor({
  initial,
  onChange,
  version = 0,
  addPointSignal = 0,
}: {
  /** Starting shape — normally GEO-04's approximate rectangle. */
  initial: LatLngPoint[];
  /** Fires on every edit with the current ring. */
  onChange: (points: LatLngPoint[]) => void;
  /** Bump to discard edits and rebuild from `initial` (the Reset button). */
  version?: number;
  /** Bump to insert a new corner at the midpoint of the shape's longest
   *  edge — the explicit "Add Point" button, for anyone who'd rather tap
   *  a button than find and drag the (small, easy-to-miss) midpoint
   *  handle themselves. Same underlying insert_at as dragging one. */
  addPointSignal?: number;
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

    // Raster-traced outlines (Solar API mask, vision detection) can come
    // back as 80-150+ near-collinear points — unusable as drag handles.
    // Reduce to the shape's real corners before anyone has to touch it;
    // see lib/geo/simplify.ts for why this is safe accuracy-wise.
    const startingShape = simplifyBoundary(initial);

    const shape = new google.maps.Polygon({
      paths: startingShape,
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

  // Tracks the addPointSignal value already handled, so this only fires
  // on a genuine bump from the parent (not on mount, and not again after
  // `version` rebuilds the polygon with the same signal value it had
  // before).
  const handledSignal = useRef(addPointSignal);
  useEffect(() => {
    if (addPointSignal === handledSignal.current) return;
    handledSignal.current = addPointSignal;

    const shape = polygon.current;
    if (!shape) return;
    const path = shape.getPath();
    const points = path.getArray();
    if (points.length < 2) return;

    // Longest edge, not always edge 0->1 — that's the one a drag can
    // actually separate into two visibly distinct corners instead of
    // landing on top of its neighbours. Degrees-latitude/longitude
    // distance, scaled by cos(lat) for the longitude term, is plenty
    // accurate for comparing edge lengths within one small roof.
    let bestIndex = 0;
    let bestLength = -1;
    for (let i = 0; i < points.length; i += 1) {
      const a = points[i];
      const b = points[(i + 1) % points.length];
      const latRad = (a.lat() * Math.PI) / 180;
      const dLat = b.lat() - a.lat();
      const dLng = (b.lng() - a.lng()) * Math.cos(latRad);
      const length = Math.hypot(dLat, dLng);
      if (length > bestLength) {
        bestLength = length;
        bestIndex = i;
      }
    }

    const a = points[bestIndex];
    const b = points[(bestIndex + 1) % points.length];
    const midpoint = new google.maps.LatLng((a.lat() + b.lat()) / 2, (a.lng() + b.lng()) / 2);
    // insert_at fires the same "set_at"/publish listener already wired
    // above, so this is indistinguishable downstream from a manual
    // midpoint drag.
    path.insertAt(bestIndex + 1, midpoint);
  }, [addPointSignal]);

  return null;
}
