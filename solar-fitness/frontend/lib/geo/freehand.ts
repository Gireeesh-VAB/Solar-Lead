// Turns a freehand stroke (the pixels a finger or mouse passed over) into a
// clean obstacle outline: a handful of corners, never crossing itself.
//
// Pure functions on screen pixels, no map and no DOM, so the behaviour is
// easy to reason about and to check. The map layer (components/map/
// FreehandDrawLayer.tsx) collects the stroke and converts the result back to
// lat/lng.
//
//   stroke (hundreds of points)
//     -> Ramer-Douglas-Peucker: keep only the points that change direction
//     -> if the loop crosses itself, take its convex hull instead (always a
//        valid shape, and a good fit for tanks, plant rooms, AC units)
//     -> reject a speck / a scribble with no area
//
// The customer then fine-tunes the corners with the boundary editor, so this
// only has to be a good starting shape.

export interface Pt {
  x: number;
  y: number;
}

export interface StrokeOptions {
  /** A stroke with fewer raw points than this is a tap, not a drawing. */
  minRawPoints?: number;
  /** Corners may be this far (px) from the traced line when simplifying. */
  tolerancePx?: number;
  /** The outline is simplified harder until it has no more corners than this. */
  maxVertices?: number;
  /** An outline smaller than this (px²) is a speck, not an obstacle. */
  minAreaPx?: number;
}

const DEFAULTS: Required<StrokeOptions> = { minRawPoints: 8, tolerancePx: 3, maxVertices: 16, minAreaPx: 150 };

function perpendicularDistance(p: Pt, a: Pt, b: Pt): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len === 0) return Math.hypot(p.x - a.x, p.y - a.y);
  return Math.abs(dy * p.x - dx * p.y + b.x * a.y - b.y * a.x) / len;
}

/** Ramer-Douglas-Peucker: the fewest points that stay within `epsilon` of the traced path. Keeps both ends. */
export function simplifyPath(points: Pt[], epsilon: number): Pt[] {
  if (points.length < 3) return points.slice();
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = keep[points.length - 1] = true;
  const stack: [number, number][] = [[0, points.length - 1]];
  while (stack.length) {
    const [lo, hi] = stack.pop()!;
    let worst = -1;
    let worstDist = epsilon;
    for (let i = lo + 1; i < hi; i += 1) {
      const d = perpendicularDistance(points[i], points[lo], points[hi]);
      if (d > worstDist) {
        worst = i;
        worstDist = d;
      }
    }
    if (worst !== -1) {
      keep[worst] = true;
      stack.push([lo, worst], [worst, hi]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

/** Absolute area of the polygon (shoelace). */
export function polygonArea(points: Pt[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

function cross(o: Pt, a: Pt, b: Pt): number {
  return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
}

/** Convex hull (Andrew's monotone chain), counter-clockwise, no repeated first point. */
export function convexHull(points: Pt[]): Pt[] {
  const pts = [...points].sort((p, q) => p.x - q.x || p.y - q.y);
  if (pts.length < 3) return pts;
  const lower: Pt[] = [];
  for (const p of pts) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: Pt[] = [];
  for (const p of [...pts].reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

function segmentsCross(a: Pt, b: Pt, c: Pt, d: Pt): boolean {
  const d1 = cross(a, b, c);
  const d2 = cross(a, b, d);
  const d3 = cross(c, d, a);
  const d4 = cross(c, d, b);
  return ((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0));
}

/** True if any two non-neighbouring edges of the closed polygon cross. */
export function selfIntersects(points: Pt[]): boolean {
  const n = points.length;
  if (n < 4) return false;
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const adjacent = j === i + 1 || (i === 0 && j === n - 1);
      if (adjacent) continue;
      if (segmentsCross(points[i], points[(i + 1) % n], points[j], points[(j + 1) % n])) return true;
    }
  }
  return false;
}

/**
 * The outline for a finished stroke, or null when it was not a real drawing
 * (a tap, a speck, a straight line). The result is closed implicitly (the
 * last corner joins the first), has at least 3 and at most `maxVertices`
 * corners, and does not cross itself.
 */
export function strokeToOutline(raw: Pt[], options: StrokeOptions = {}): Pt[] | null {
  const o = { ...DEFAULTS, ...options };
  if (raw.length < o.minRawPoints) return null;

  let epsilon = o.tolerancePx;
  let pts = simplifyPath(raw, epsilon);
  // Tighten the shape until it is a handful of corners the customer can handle.
  while (pts.length > o.maxVertices) {
    epsilon *= 1.4;
    pts = simplifyPath(raw, epsilon);
  }
  // A stroke that ends back near where it began would leave two corners on top of each other.
  if (pts.length > 3 && Math.hypot(pts[0].x - pts[pts.length - 1].x, pts[0].y - pts[pts.length - 1].y) <= Math.max(epsilon, 4)) {
    pts = pts.slice(0, -1);
  }
  if (pts.length < 3) return null;

  // A loop that crosses itself is not a valid shape: use the smallest convex shape around the stroke.
  if (selfIntersects(pts)) pts = convexHull(pts);
  if (pts.length < 3 || polygonArea(pts) < o.minAreaPx) return null;
  return pts;
}
