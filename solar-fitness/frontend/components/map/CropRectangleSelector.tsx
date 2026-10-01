"use client";

// Crop selection mode (StartCheckWizard's "Select Building" step): a
// resizeable/draggable/ROTATABLE rectangle the customer positions over
// their building. The rectangle is ONLY a locator — its center is sent to
// resolve-building to find the actual structure inside it; the rectangle
// itself is never treated as the rooftop (see BuildingSelector.tsx).
//
// Google Maps' native <Rectangle> (google.maps.Rectangle) has NO rotation
// support at all — it's defined purely by a LatLngBounds (north/south/
// east/west), which is mathematically always axis-aligned. Many real
// buildings sit at an angle on the map, so an axis-aligned-only rectangle
// can never snugly cover one. This is therefore built the same way
// RoofBoundaryEditor.tsx builds its editable polygon: an imperative
// google.maps.Polygon for the shape itself, plus hand-rolled
// google.maps.Marker handles (4 corners, 4 edge midpoints, 1 rotate
// handle) — nothing in the Maps JS API gives rotation for free.
//
// All geometry (resize, rotate, translate) is done in a local flat-earth
// metric frame centered on the rectangle (meters east/north from
// `center`), which is accurate enough at this scale (a single building)
// — the same approximation engine/projection.py documents as fine for
// small, local distances, and the same one defaultCropBounds used before.

import { useEffect, useRef } from "react";
import { useMap } from "@vis.gl/react-google-maps";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";

export interface RotatedRect {
  center: LatLngPoint;
  /** Half-extent (metres) along the rectangle's own local width axis,
   *  before rotation is applied. */
  halfWidthM: number;
  /** Half-extent (metres) along the rectangle's own local height axis,
   *  before rotation is applied. */
  halfHeightM: number;
  /** Clockwise degrees from north — same convention as this app's roof
   *  azimuth values (compass_direction / azimuthDeg), so a rotated crop
   *  rectangle's angle reads the same way a roof's own azimuth does. */
  rotationDeg: number;
}

// Brand emerald — matches --brand in app/globals.css. Canvas/Maps drawing
// needs a real color value, CSS custom properties don't resolve here.
const STROKE = "#1e7a5f";
const FILL = "#1e7a5f";

const METERS_PER_DEG_LAT = 111_320;
const MIN_HALF_WIDTH_M = 1.5; // 3m minimum side — small enough to shrink a lot, never degenerate.
const ROTATE_HANDLE_GAP_M = 4; // how far the rotate handle floats above the rectangle's north edge.

function metersPerDegLng(lat: number): number {
  return METERS_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180);
}

/** Local metric offset (east metres, north metres) from `center` -> lat/lng. */
function localToLatLng(center: LatLngPoint, eastM: number, northM: number): LatLngPoint {
  return {
    lat: center.lat + northM / METERS_PER_DEG_LAT,
    lng: center.lng + eastM / metersPerDegLng(center.lat),
  };
}

/** lat/lng -> local metric offset (east metres, north metres) from `center`. */
function latLngToLocal(center: LatLngPoint, point: LatLngPoint): { x: number; y: number } {
  return {
    x: (point.lng - center.lng) * metersPerDegLng(center.lat),
    y: (point.lat - center.lat) * METERS_PER_DEG_LAT,
  };
}

/** Rotates a local (east, north) offset by `deg` CLOCKWISE from north —
 *  e.g. rotateCW(0, 1, 90) (due north) -> (1, 0) (due east). */
function rotateCW(x: number, y: number, deg: number): { x: number; y: number } {
  const rad = (deg * Math.PI) / 180;
  const cos = Math.cos(rad);
  const sin = Math.sin(rad);
  return { x: x * cos + y * sin, y: -x * sin + y * cos };
}

function normalizeDeg(deg: number): number {
  return ((deg % 360) + 360) % 360;
}

/** A default crop roughly building-sized (~24m square) centered on `center`, unrotated. */
export function defaultCropRect(center: LatLngPoint, sizeM = 24): RotatedRect {
  return { center, halfWidthM: sizeM / 2, halfHeightM: sizeM / 2, rotationDeg: 0 };
}

export function rectCenter(rect: RotatedRect): LatLngPoint {
  return rect.center;
}

/** The rectangle's 4 corners, in order NW, NE, SE, SW, accounting for rotation. */
export function rectToCorners(rect: RotatedRect): LatLngPoint[] {
  const local: [number, number][] = [
    [-rect.halfWidthM, rect.halfHeightM],
    [rect.halfWidthM, rect.halfHeightM],
    [rect.halfWidthM, -rect.halfHeightM],
    [-rect.halfWidthM, -rect.halfHeightM],
  ];
  return local.map(([x, y]) => {
    const r = rotateCW(x, y, rect.rotationDeg);
    return localToLatLng(rect.center, r.x, r.y);
  });
}

/** Edge midpoints, in order N, E, S, W, accounting for rotation. */
function edgeMidpoints(rect: RotatedRect): LatLngPoint[] {
  const local: [number, number][] = [
    [0, rect.halfHeightM],
    [rect.halfWidthM, 0],
    [0, -rect.halfHeightM],
    [-rect.halfWidthM, 0],
  ];
  return local.map(([x, y]) => {
    const r = rotateCW(x, y, rect.rotationDeg);
    return localToLatLng(rect.center, r.x, r.y);
  });
}

function rotateHandlePoint(rect: RotatedRect): LatLngPoint {
  const r = rotateCW(0, rect.halfHeightM + ROTATE_HANDLE_GAP_M, rect.rotationDeg);
  return localToLatLng(rect.center, r.x, r.y);
}

function makeHandleMarker(map: google.maps.Map, cursor: string, title: string): google.maps.Marker {
  return new google.maps.Marker({
    position: { lat: 0, lng: 0 },
    map,
    draggable: true,
    cursor,
    title,
    zIndex: 6,
    icon: {
      path: google.maps.SymbolPath.CIRCLE,
      scale: 5,
      fillColor: "#ffffff",
      fillOpacity: 1,
      strokeColor: STROKE,
      strokeWeight: 2,
    },
  });
}

export function CropRectangleSelector({
  initialRect,
  onChange,
  version = 0,
}: {
  initialRect: RotatedRect;
  /** Fires on every resize/reposition/rotate with the current rect. */
  onChange: (rect: RotatedRect) => void;
  /** Bump to discard edits and rebuild from `initialRect` (the Reset button). */
  version?: number;
}) {
  const map = useMap();
  // Kept in a ref so the effect below does not re-run on every parent
  // render — same reasoning as RoofBoundaryEditor.tsx's `emit` ref.
  const emit = useRef(onChange);
  useEffect(() => {
    emit.current = onChange;
  }, [onChange]);

  useEffect(() => {
    if (!map) return;

    const rectRef = { current: initialRect };
    const shape = new google.maps.Polygon({
      paths: rectToCorners(initialRect),
      strokeColor: STROKE,
      strokeOpacity: 0.95,
      strokeWeight: 2,
      fillColor: FILL,
      fillOpacity: 0.1,
      draggable: true,
      zIndex: 5,
      map,
    });

    const cornerMarkers = [
      makeHandleMarker(map, "pointer", "Drag to resize"), // NW
      makeHandleMarker(map, "pointer", "Drag to resize"), // NE
      makeHandleMarker(map, "pointer", "Drag to resize"), // SE
      makeHandleMarker(map, "pointer", "Drag to resize"), // SW
    ];
    const edgeMarkers = [
      makeHandleMarker(map, "pointer", "Drag to resize"), // N
      makeHandleMarker(map, "pointer", "Drag to resize"), // E
      makeHandleMarker(map, "pointer", "Drag to resize"), // S
      makeHandleMarker(map, "pointer", "Drag to resize"), // W
    ];
    const rotateMarker = new google.maps.Marker({
      position: rotateHandlePoint(initialRect),
      map,
      draggable: true,
      cursor: "grab",
      title: "Drag to rotate",
      zIndex: 7,
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 6,
        fillColor: STROKE,
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 2,
      },
    });
    const rotateLine = new google.maps.Polyline({
      path: [edgeMidpoints(initialRect)[0], rotateHandlePoint(initialRect)],
      strokeColor: STROKE,
      strokeOpacity: 0.7,
      strokeWeight: 1.5,
      clickable: false,
      zIndex: 6,
      map,
    });

    /** Moves every handle marker (and the rotate line) to match
     *  rectRef.current — never touches the polygon's own path, so this is
     *  safe to call mid-drag of the polygon body itself, where Maps is
     *  already moving the polygon's path natively and re-setting it here
     *  would fight that native drag frame-by-frame. */
    const syncHandles = () => {
      const rect = rectRef.current;
      const corners = rectToCorners(rect);
      corners.forEach((p, i) => cornerMarkers[i].setPosition(p));
      const mids = edgeMidpoints(rect);
      mids.forEach((p, i) => edgeMarkers[i].setPosition(p));
      const handlePos = rotateHandlePoint(rect);
      rotateMarker.setPosition(handlePos);
      rotateLine.setPath([mids[0], handlePos]);
    };

    /** Full redraw, including the polygon's own path — for every edit
     *  EXCEPT the polygon body's own drag (see syncHandles above). */
    const redraw = () => {
      shape.setPath(rectToCorners(rectRef.current));
      syncHandles();
    };

    const publish = () => emit.current(rectRef.current);

    // Whole-shape drag: reposition, translating center by the cursor's
    // own delta since the drag started. Native Polygon dragging already
    // moves the polygon's path itself; this only keeps rectRef and the
    // handle markers in sync with it.
    let dragStart: { latLng: google.maps.LatLng; rect: RotatedRect } | null = null;
    const bodyListeners = [
      shape.addListener("dragstart", (e: google.maps.MapMouseEvent) => {
        if (!e.latLng) return;
        dragStart = { latLng: e.latLng, rect: rectRef.current };
      }),
      shape.addListener("drag", (e: google.maps.MapMouseEvent) => {
        if (!dragStart || !e.latLng) return;
        const dLat = e.latLng.lat() - dragStart.latLng.lat();
        const dLng = e.latLng.lng() - dragStart.latLng.lng();
        rectRef.current = {
          ...dragStart.rect,
          center: { lat: dragStart.rect.center.lat + dLat, lng: dragStart.rect.center.lng + dLng },
        };
        syncHandles();
      }),
      shape.addListener("dragend", () => {
        dragStart = null;
        publish();
      }),
    ];

    // Corner handles resize BOTH dimensions, anchored on the OPPOSITE
    // corner (matches how google.maps.Rectangle's own resize handles
    // behaved before this rewrite) — sx/sy is which corner each marker
    // is, in the rectangle's own unrotated local frame.
    const cornerSigns: [number, number][] = [
      [-1, 1], // NW
      [1, 1], // NE
      [1, -1], // SE
      [-1, -1], // SW
    ];
    const cornerListeners = cornerMarkers.flatMap((marker, i) => {
      const [sx, sy] = cornerSigns[i];
      return [
        marker.addListener("drag", (e: google.maps.MapMouseEvent) => {
          if (!e.latLng) return;
          const rect = rectRef.current;
          const world = latLngToLocal(rect.center, { lat: e.latLng.lat(), lng: e.latLng.lng() });
          const local = rotateCW(world.x, world.y, -rect.rotationDeg); // into the unrotated frame
          const fixedX = -sx * rect.halfWidthM;
          const fixedY = -sy * rect.halfHeightM;
          const halfWidthM = Math.max(MIN_HALF_WIDTH_M, Math.abs(local.x - fixedX) / 2);
          const halfHeightM = Math.max(MIN_HALF_WIDTH_M, Math.abs(local.y - fixedY) / 2);
          const centerLocal = { x: (local.x + fixedX) / 2, y: (local.y + fixedY) / 2 };
          const centerWorld = rotateCW(centerLocal.x, centerLocal.y, rect.rotationDeg);
          rectRef.current = {
            center: localToLatLng(rect.center, centerWorld.x, centerWorld.y),
            halfWidthM,
            halfHeightM,
            rotationDeg: rect.rotationDeg,
          };
          redraw();
        }),
        marker.addListener("dragend", publish),
      ];
    });

    // Edge handles resize ONE dimension, anchored on the opposite edge.
    const edgeDefs: { sx: number; sy: number; axis: "w" | "h" }[] = [
      { sx: 0, sy: 1, axis: "h" }, // N
      { sx: 1, sy: 0, axis: "w" }, // E
      { sx: 0, sy: -1, axis: "h" }, // S
      { sx: -1, sy: 0, axis: "w" }, // W
    ];
    const edgeListeners = edgeMarkers.flatMap((marker, i) => {
      const { sx, sy, axis } = edgeDefs[i];
      return [
        marker.addListener("drag", (e: google.maps.MapMouseEvent) => {
          if (!e.latLng) return;
          const rect = rectRef.current;
          const world = latLngToLocal(rect.center, { lat: e.latLng.lat(), lng: e.latLng.lng() });
          const local = rotateCW(world.x, world.y, -rect.rotationDeg);
          if (axis === "h") {
            const fixedY = -sy * rect.halfHeightM;
            const halfHeightM = Math.max(MIN_HALF_WIDTH_M, Math.abs(local.y - fixedY) / 2);
            const centerLocalY = (local.y + fixedY) / 2;
            const centerWorld = rotateCW(0, centerLocalY, rect.rotationDeg);
            rectRef.current = {
              center: localToLatLng(rect.center, centerWorld.x, centerWorld.y),
              halfWidthM: rect.halfWidthM,
              halfHeightM,
              rotationDeg: rect.rotationDeg,
            };
          } else {
            const fixedX = -sx * rect.halfWidthM;
            const halfWidthM = Math.max(MIN_HALF_WIDTH_M, Math.abs(local.x - fixedX) / 2);
            const centerLocalX = (local.x + fixedX) / 2;
            const centerWorld = rotateCW(centerLocalX, 0, rect.rotationDeg);
            rectRef.current = {
              center: localToLatLng(rect.center, centerWorld.x, centerWorld.y),
              halfWidthM,
              halfHeightM: rect.halfHeightM,
              rotationDeg: rect.rotationDeg,
            };
          }
          redraw();
        }),
        marker.addListener("dragend", publish),
      ];
    });

    // Rotate handle: the new rotation is simply the handle's own bearing
    // from the (fixed, unmoving) center — it always sits along the
    // rectangle's local north axis before rotation, so its world bearing
    // IS the rectangle's new rotation angle directly.
    const rotateListeners = [
      rotateMarker.addListener("drag", (e: google.maps.MapMouseEvent) => {
        if (!e.latLng) return;
        const rect = rectRef.current;
        const offset = latLngToLocal(rect.center, { lat: e.latLng.lat(), lng: e.latLng.lng() });
        const rotationDeg = normalizeDeg((Math.atan2(offset.x, offset.y) * 180) / Math.PI);
        rectRef.current = { ...rect, rotationDeg };
        redraw();
      }),
      rotateMarker.addListener("dragend", publish),
    ];

    publish();

    return () => {
      [...bodyListeners, ...cornerListeners, ...edgeListeners, ...rotateListeners].forEach((l) => l.remove());
      google.maps.event.clearInstanceListeners(shape);
      shape.setMap(null);
      [...cornerMarkers, ...edgeMarkers, rotateMarker].forEach((m) => {
        google.maps.event.clearInstanceListeners(m);
        m.setMap(null);
      });
      rotateLine.setMap(null);
    };
    // `initialRect` is intentionally not a dependency: it is the STARTING
    // shape, and rebuilding on every parent render would wipe the user's
    // work mid-edit. `version` is the explicit "start again" signal —
    // same convention as RoofBoundaryEditor.tsx.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, version]);

  return null;
}
