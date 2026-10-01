import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";

/** Rough plan-view area, only to catch a nonsense shape client-side before
 *  saving — the authoritative measurement is the backend's projected one.
 *
 *  Shared by BoundaryEditorClient.tsx (post-creation "is this your roof?"
 *  correction) and RoofCropEditor.tsx (StartCheckWizard's pre-creation
 *  crop step) so there is exactly one client-side area-sanity
 *  implementation, not two that can drift apart. */
export function approxAreaM2(points: LatLngPoint[]): number {
  if (points.length < 3) return 0;
  const lat0 = (points.reduce((s, p) => s + p.lat, 0) / points.length) * (Math.PI / 180);
  const mPerLat = 111_320;
  const mPerLng = 111_320 * Math.cos(lat0);
  let twice = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    twice += a.lng * mPerLng * (b.lat * mPerLat) - b.lng * mPerLng * (a.lat * mPerLat);
  }
  return Math.abs(twice) / 2;
}

/** A roof smaller than this is almost certainly a mis-drag, not a
 *  building — worth catching before it becomes someone's system size. */
export const MIN_PLAUSIBLE_ROOF_AREA_M2 = 5;

/** The area-weighted centroid of a polygon, in the same local flat-earth
 *  metre frame as approxAreaM2() above, converted back to lat/lng.
 *
 *  Mirrors backend/src/solarfit/providers/solar_api.py::polygon_centroid()
 *  — same reasoning: whenever a boundary polygon is replaced or edited
 *  (here, the customer dragging corners in the "Adjust boundary" step),
 *  any centroid used to recentre a later step's map MUST be recomputed
 *  from that edited polygon, never left over from an earlier, now-stale
 *  boundary (the original crop rectangle / detected building) — that
 *  mismatch is what makes a correctly-edited boundary look like it
 *  "moved away" once the next step's map centres on the stale point
 *  instead of the polygon actually being shown.
 *
 *  Falls back to a plain vertex average for a degenerate (near-zero-area)
 *  shape, where the area-weighted formula divides by ~0. */
export function polygonCentroid(points: LatLngPoint[]): LatLngPoint {
  if (points.length === 0) return { lat: 0, lng: 0 };
  if (points.length < 3) {
    return {
      lat: points.reduce((s, p) => s + p.lat, 0) / points.length,
      lng: points.reduce((s, p) => s + p.lng, 0) / points.length,
    };
  }

  const lat0 = (points.reduce((s, p) => s + p.lat, 0) / points.length) * (Math.PI / 180);
  const mPerLat = 111_320;
  const mPerLng = 111_320 * Math.cos(lat0);
  const xy = points.map((p) => ({ x: p.lng * mPerLng, y: p.lat * mPerLat }));

  let signedArea = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < xy.length; i++) {
    const a = xy[i];
    const b = xy[(i + 1) % xy.length];
    const cross = a.x * b.y - b.x * a.y;
    signedArea += cross;
    cx += (a.x + b.x) * cross;
    cy += (a.y + b.y) * cross;
  }
  signedArea /= 2;

  if (Math.abs(signedArea) < 1e-6) {
    return {
      lat: points.reduce((s, p) => s + p.lat, 0) / points.length,
      lng: points.reduce((s, p) => s + p.lng, 0) / points.length,
    };
  }

  cx /= 6 * signedArea;
  cy /= 6 * signedArea;
  return { lat: cy / mPerLat, lng: cx / mPerLng };
}
