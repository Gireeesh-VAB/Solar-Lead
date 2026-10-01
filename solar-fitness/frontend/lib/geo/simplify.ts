import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";

// Solar API / vision-detected roof outlines are traced from raster
// imagery — a real rooftop with 4-8 actual corners can come back as a
// ring of 80-150+ points, each one a tiny raster-staircase jog a couple
// of centimetres long. Handed straight to the boundary editor, that's
// unusable: the corner handles sit on top of each other and there's
// nothing left to drag onto an actual roof edge.
//
// Ramer-Douglas-Peucker collapses runs of near-collinear points down to
// the handful that actually change direction, within `toleranceMeters`
// of the original line — so the simplified ring still hugs the real
// rooftop silhouette that closely, it just doesn't have a handle for
// every pixel of staircase noise along the way. The user's own further
// dragging/adding/removing on top of this is where final accuracy
// against their actual roof comes from either way, exactly as before.

/** Local planar (x=east metres, y=north metres) projection around the
 *  ring's own mean latitude — accurate enough at building scale, and
 *  avoids doing polygon simplification in degrees where a metre of
 *  longitude and a metre of latitude aren't the same size. */
function toLocalMeters(points: LatLngPoint[]): { xy: [number, number][]; refLat: number; refLng: number } {
  const refLat = points.reduce((s, p) => s + p.lat, 0) / points.length;
  const refLng = points.reduce((s, p) => s + p.lng, 0) / points.length;
  const mPerLat = 111_320;
  const mPerLng = 111_320 * Math.cos((refLat * Math.PI) / 180);
  return {
    xy: points.map((p): [number, number] => [(p.lng - refLng) * mPerLng, (p.lat - refLat) * mPerLat]),
    refLat,
    refLng,
  };
}

function fromLocalMeters(xy: [number, number][], refLat: number, refLng: number): LatLngPoint[] {
  const mPerLat = 111_320;
  const mPerLng = 111_320 * Math.cos((refLat * Math.PI) / 180);
  return xy.map(([x, y]) => ({ lat: refLat + y / mPerLat, lng: refLng + x / mPerLng }));
}

function perpendicularDistance(point: [number, number], a: [number, number], b: [number, number]): number {
  const [px, py] = point;
  const [ax, ay] = a;
  const [bx, by] = b;
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
  const projX = ax + t * dx;
  const projY = ay + t * dy;
  return Math.hypot(px - projX, py - projY);
}

/** Classic Douglas-Peucker over an open polyline (first/last points are
 *  always kept). */
function rdp(points: [number, number][], epsilon: number): [number, number][] {
  if (points.length < 3) return points;
  let maxDist = -1;
  let index = 0;
  const end = points.length - 1;
  for (let i = 1; i < end; i += 1) {
    const d = perpendicularDistance(points[i], points[0], points[end]);
    if (d > maxDist) {
      maxDist = d;
      index = i;
    }
  }
  if (maxDist > epsilon) {
    const left = rdp(points.slice(0, index + 1), epsilon);
    const right = rdp(points.slice(index), epsilon);
    return left.slice(0, -1).concat(right);
  }
  return [points[0], points[end]];
}

/** Simplifies a closed ring (no repeated first/last point) down to its
 *  main corners, within `toleranceMeters` of the original outline.
 *
 *  Douglas-Peucker is defined for an open polyline with two fixed
 *  endpoints; a ring has none. The standard fix — split the ring at its
 *  two most distant points into two chains, simplify each as an open
 *  polyline, then stitch the results back together — is what happens
 *  below. */
export function simplifyBoundary(points: LatLngPoint[], toleranceMeters = 3): LatLngPoint[] {
  // Some sources close the ring explicitly (first === last); drop the
  // duplicate so it isn't treated as a real corner.
  let ring = points;
  if (ring.length > 1) {
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (Math.abs(first.lat - last.lat) < 1e-9 && Math.abs(first.lng - last.lng) < 1e-9) {
      ring = ring.slice(0, -1);
    }
  }
  if (ring.length <= 4) return ring;

  const { xy, refLat, refLng } = toLocalMeters(ring);

  let farIndex = 1;
  let farDist = -1;
  for (let i = 1; i < xy.length; i += 1) {
    const d = Math.hypot(xy[i][0] - xy[0][0], xy[i][1] - xy[0][1]);
    if (d > farDist) {
      farDist = d;
      farIndex = i;
    }
  }

  const chainA = xy.slice(0, farIndex + 1);
  const chainB = xy.slice(farIndex).concat([xy[0]]);
  const simplifiedA = rdp(chainA, toleranceMeters);
  const simplifiedB = rdp(chainB, toleranceMeters);
  const combined = simplifiedA.slice(0, -1).concat(simplifiedB.slice(0, -1));

  // Simplification should never leave less than a triangle — fall back
  // to the original ring rather than hand back something degenerate.
  if (combined.length < 3) return ring;

  return fromLocalMeters(combined, refLat, refLng);
}
