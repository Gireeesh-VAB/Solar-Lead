import type { ConstraintKind, Verdict } from "@/lib/types";

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export function formatKwp(value: number): string {
  return `${value.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWp`;
}

export function formatInr(value: number): string {
  return `Rs ${Math.round(value).toLocaleString("en-IN")}`;
}

export function formatPercent(value: number, fractionDigits = 1): string {
  return `${value.toFixed(fractionDigits)}%`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "2-digit" });
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** Area of a lat/lng ring in square metres, via the shoelace formula on
 *  an equirectangular projection local to the ring's own first point.
 *  Panels and roof segments are small enough (a few metres to tens of
 *  metres across) that this local flat approximation's error is
 *  negligible — nowhere near the "survey-grade" claims §17 forbids, but
 *  fine for a coverage percentage the customer reads as approximate. */
export function polygonAreaM2(ring: { lat: number; lng: number }[]): number {
  if (ring.length < 3) return 0;
  const originLat = ring[0].lat;
  const metersPerDegLat = 110_574;
  const metersPerDegLng = 111_320 * Math.cos((originLat * Math.PI) / 180);
  const points = ring.map((p) => ({
    x: (p.lng - ring[0].lng) * metersPerDegLng,
    y: (p.lat - ring[0].lat) * metersPerDegLat,
  }));
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

export const VERDICT_LABEL: Record<Verdict, string> = {
  SUITABLE: "Suitable",
  SUITABLE_SUBJECT_TO_SURVEY: "Suitable, subject to survey",
  CONDITIONAL: "Conditional",
  INSUFFICIENT_DATA: "Insufficient data",
  NOT_SUITABLE: "Not suitable",
};

export const CONSTRAINT_KIND_LABEL: Record<ConstraintKind, string> = {
  physical: "Physical",
  regulatory: "Regulatory",
  commercial: "Commercial",
};

export function siteTypeLabel(type: string): string {
  switch (type) {
    case "ROOFTOP_GOVT":
      return "Rooftop — Government";
    case "ROOFTOP_RESIDENTIAL":
      return "Rooftop — Residential";
    case "ROOFTOP_CI":
      return "Rooftop — Commercial & Industrial";
    case "FLOATING":
      return "Floating";
    default:
      return type;
  }
}
