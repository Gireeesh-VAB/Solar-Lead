"use client";

// Freehand selection mode (StartCheckWizard's "Select Building" step):
// click directly on the map to place boundary points one at a time — the
// first click places the first corner, every next click adds another
// (no "Add point" button needed for that), and the boundary line grows to
// connect them live. No starting shape to drag into place: the customer
// traces the roof outline themselves, then presses "Finish boundary" (see
// `isDrawing` below) to close the ring back to its first point and switch
// over to drag-to-adjust.
//
// Google's own google.maps.Polygon `editable` mode (used by
// RoofBoundaryEditor, one step later) is deliberately NOT used here: it
// also renders a midpoint handle between every pair of vertices, and
// dragging one inserts a corner — a different interaction model than the
// explicit click-to-place-then-finish flow this component implements.
// Each corner is its own `google.maps.Marker`, independently draggable
// from the moment it's placed; markers are rebuilt (not just repositioned)
// whenever a point is added, since every marker after the insertion point
// shifts index.
//
// While still drawing (`isDrawing`), the boundary renders as an open
// polyline — it must NOT visually close into a filled shape until the
// customer actually finishes, or a 2-3 point in-progress trace would look
// like a (wrong) tiny closed polygon. Finishing swaps it for a closed,
// filled google.maps.Polygon — the same shape the "Add point" button
// (still available afterwards, for L-shaped/T-shaped/irregular
// refinement) and point-dragging both continue to operate on.

import { useEffect, useRef } from "react";
import { useMap } from "@vis.gl/react-google-maps";
import type { LatLngPoint } from "./RoofBoundaryEditor";

// Brand emerald — matches --brand in app/globals.css. Canvas/Maps drawing
// needs a real color value, CSS custom properties don't resolve here.
const STROKE = "#1e7a5f";
const FILL = "#1e7a5f";

// Two clicks this close together almost always mean "the same tap
// registered twice" (a slightly shaky finger/mouse), not two genuinely
// distinct corners a real roof would have — dropped rather than added as
// a near-duplicate point that would just sit invisibly on top of its
// neighbour.
const MIN_POINT_SPACING_M = 0.5;

/** Approximate planar distance in metres between two nearby lat/lng
 *  points — degrees scaled by cos(lat) for the longitude term and a fixed
 *  metres-per-degree, plenty accurate at building scale. Same technique
 *  `longestEdgeIndex` below uses for edge lengths. */
function approxMetersBetween(a: LatLngPoint, b: LatLngPoint): number {
  const latRad = (a.lat * Math.PI) / 180;
  const dLat = (b.lat - a.lat) * 111_320;
  const dLng = (b.lng - a.lng) * Math.cos(latRad) * 111_320;
  return Math.hypot(dLat, dLng);
}

/** Index of the longest edge (i -> i+1) in a ring of points — the edge
 *  whose midpoint a new corner can actually separate into two visibly
 *  distinct points instead of landing on top of its neighbours. Degrees
 *  lat/lng, scaled by cos(lat) for the longitude term, is plenty accurate
 *  for comparing edge lengths within one small roof. Shared with
 *  RoofBoundaryEditor's own copy of this same calculation. */
function longestEdgeIndex(points: LatLngPoint[]): number {
  let bestIndex = 0;
  let bestLength = -1;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const latRad = (a.lat * Math.PI) / 180;
    const dLat = b.lat - a.lat;
    const dLng = (b.lng - a.lng) * Math.cos(latRad);
    const length = Math.hypot(dLat, dLng);
    if (length > bestLength) {
      bestLength = length;
      bestIndex = i;
    }
  }
  return bestIndex;
}

export function FreehandPolygonSelector({
  initial,
  onChange,
  version = 0,
  addPointSignal = 0,
  isDrawing,
}: {
  /** Starting corners — normally empty ([]), so the customer starts from a
   *  blank map and places every point by clicking. The component doesn't
   *  assume empty, but nothing today seeds it non-empty. */
  initial: LatLngPoint[];
  /** Fires with the current corners on every click-to-add, drag, and
   *  added point. */
  onChange: (points: LatLngPoint[]) => void;
  /** Bump to discard edits and rebuild from `initial` (the Reset/Clear button). */
  version?: number;
  /** Bump to insert a new corner at the midpoint of the shape's longest
   *  edge — the explicit "Add point" button, available once finished. */
  addPointSignal?: number;
  /** true while the customer is still placing points by clicking the map;
   *  false once "Finish boundary" has been pressed. Clicking the map only
   *  adds a point while this is true; flipping it false closes the ring
   *  (last point connects back to the first) without moving any point. */
  isDrawing: boolean;
}) {
  const map = useMap();
  const pointsRef = useRef<LatLngPoint[]>(initial);
  const drawingRef = useRef(isDrawing);
  const polygon = useRef<google.maps.Polygon | null>(null);
  const line = useRef<google.maps.Polyline | null>(null);
  const markers = useRef<google.maps.Marker[]>([]);
  const emit = useRef(onChange);
  // Set by the mount effect below, called by the addPointSignal effect and
  // the map-click handler — one marker-(re)building implementation shared
  // by "the shape just got created", "a point was clicked in", and "a
  // point was inserted via Add point".
  const rebuildMarkers = useRef<() => void>(() => {});
  // Same sharing, for swapping between the open in-progress line and the
  // closed finished polygon.
  const syncOverlay = useRef<() => void>(() => {});

  useEffect(() => {
    emit.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!map) return;

    const commonStyle = {
      strokeColor: STROKE,
      strokeOpacity: 0.95,
      strokeWeight: 2,
      clickable: false,
      zIndex: 5,
    } as const;

    // Renders `pointsRef.current` as an open polyline while still drawing
    // (or with fewer than 3 points), or a closed, filled polygon once
    // finished — never both at once, and never a closed shape before the
    // customer actually finishes.
    syncOverlay.current = () => {
      const points = pointsRef.current;
      const closed = !drawingRef.current && points.length >= 3;

      if (closed) {
        if (line.current) {
          line.current.setMap(null);
          line.current = null;
        }
        if (!polygon.current) {
          polygon.current = new google.maps.Polygon({
            ...commonStyle,
            fillColor: FILL,
            fillOpacity: 0.12,
            editable: false,
            draggable: false,
            map,
          });
        }
        polygon.current.setPath(points);
        return;
      }

      if (polygon.current) {
        polygon.current.setMap(null);
        polygon.current = null;
      }
      if (points.length < 2) {
        if (line.current) {
          line.current.setMap(null);
          line.current = null;
        }
        return;
      }
      if (!line.current) {
        line.current = new google.maps.Polyline({ ...commonStyle, path: points, map });
      } else {
        line.current.setPath(points);
      }
    };

    // Replaces markers.current with one marker per current point, each
    // wired to its own (now-correct) index — the only safe way to handle
    // an insertion shifting every later corner's index.
    rebuildMarkers.current = () => {
      markers.current.forEach((m) => {
        google.maps.event.clearInstanceListeners(m);
        m.setMap(null);
      });
      markers.current = pointsRef.current.map(
        (corner) =>
          new google.maps.Marker({
            position: corner,
            map,
            draggable: true,
            zIndex: 6,
            icon: {
              path: google.maps.SymbolPath.CIRCLE,
              scale: 6,
              fillColor: STROKE,
              fillOpacity: 1,
              strokeColor: "#ffffff",
              strokeWeight: 1.5,
            },
          })
      );
      // Listeners are cleaned up via clearInstanceListeners above rather
      // than kept/removed individually — nothing else needs to reference
      // them once attached.
      markers.current.forEach((m, i) => {
        m.addListener("drag", () => {
          const pos = m.getPosition();
          if (!pos) return;
          pointsRef.current = pointsRef.current.map((p, j) =>
            j === i ? { lat: pos.lat(), lng: pos.lng() } : p
          );
          syncOverlay.current();
        });
        m.addListener("dragend", () => emit.current(pointsRef.current));
      });
    };

    pointsRef.current = initial;
    syncOverlay.current();
    rebuildMarkers.current();
    emit.current(pointsRef.current);

    // The click-to-add-a-point handler — the core of the new behaviour.
    // Only acts while `isDrawing` (read via the ref so this listener,
    // attached once per mount/version, always sees the latest value
    // without needing to be torn down and re-attached).
    const clickListener = map.addListener("click", (event: google.maps.MapMouseEvent) => {
      if (!drawingRef.current) return;
      const latLng = event.latLng;
      if (!latLng) return;
      const point: LatLngPoint = { lat: latLng.lat(), lng: latLng.lng() };

      const points = pointsRef.current;
      const last = points[points.length - 1];
      if (last && approxMetersBetween(last, point) < MIN_POINT_SPACING_M) return;

      pointsRef.current = [...points, point];
      syncOverlay.current();
      rebuildMarkers.current();
      emit.current(pointsRef.current);
    });

    return () => {
      google.maps.event.removeListener(clickListener);
      markers.current.forEach((m) => {
        google.maps.event.clearInstanceListeners(m);
        m.setMap(null);
      });
      markers.current = [];
      polygon.current?.setMap(null);
      polygon.current = null;
      line.current?.setMap(null);
      line.current = null;
    };
    // `initial` is intentionally not a dependency beyond mount/version —
    // rebuilding on every parent render would wipe a drag or a trace in
    // progress.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, version]);

  // Finishing (closing the ring) or, in principle, un-finishing doesn't
  // move any point — just swaps which overlay type renders them.
  useEffect(() => {
    drawingRef.current = isDrawing;
    syncOverlay.current();
  }, [isDrawing]);

  // Tracks the addPointSignal value already handled, so this only fires
  // on a genuine bump from the parent (not on mount, and not again after
  // `version` rebuilds with the same signal value it had before).
  const handledSignal = useRef(addPointSignal);
  useEffect(() => {
    if (addPointSignal === handledSignal.current) return;
    handledSignal.current = addPointSignal;
    if (pointsRef.current.length < 2) return;

    const points = pointsRef.current;
    const bestIndex = longestEdgeIndex(points);
    const a = points[bestIndex];
    const b = points[(bestIndex + 1) % points.length];
    const midpoint: LatLngPoint = { lat: (a.lat + b.lat) / 2, lng: (a.lng + b.lng) / 2 };

    const next = [...points];
    next.splice(bestIndex + 1, 0, midpoint);
    pointsRef.current = next;

    syncOverlay.current();
    rebuildMarkers.current();
    emit.current(pointsRef.current);
  }, [addPointSignal]);

  return null;
}
