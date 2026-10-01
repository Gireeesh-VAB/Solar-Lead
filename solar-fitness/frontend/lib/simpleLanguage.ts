// Central plain-language mappings for the simple-first customer redesign
// — technical value -> simple word/tier, never a fabricated number. Every
// function here is a presentation-only bucketing of a REAL figure already
// computed by the engine; none of them invent data.

import type { ConditionCode } from "@/lib/types";
import type { StatusTone } from "@/components/ui/SimpleStatus";

// site.shadingScore: 0 = fully shaded .. 1 = unobstructed (domain/site.py::
// ShadingEstimate). Sunlight and shade are deliberately presented as two
// views of this SAME number, not two independently-measured metrics — the
// engine has no separate shadow-source/seasonal model to draw a second
// figure from, and fabricating one would be worse than presenting one
// number twice, honestly framed.
export function sunlightTier(shadingScore: number | null | undefined): {
  label: "Excellent" | "Good" | "Average" | "Low" | "Not available";
  rating: number;
} {
  if (shadingScore == null) return { label: "Not available", rating: 0 };
  if (shadingScore >= 0.85) return { label: "Excellent", rating: 5 };
  if (shadingScore >= 0.65) return { label: "Good", rating: 4 };
  if (shadingScore >= 0.4) return { label: "Average", rating: 3 };
  return { label: "Low", rating: 2 };
}

export function shadeTier(shadingScore: number | null | undefined): {
  label: "Low" | "Medium" | "High" | "Not available";
  tone: StatusTone;
} {
  if (shadingScore == null) return { label: "Not available", tone: "check" };
  const shaded = 1 - shadingScore;
  if (shaded <= 0.15) return { label: "Low", tone: "good" };
  if (shaded <= 0.35) return { label: "Medium", tone: "check" };
  return { label: "High", tone: "bad" };
}

// domain/assessment.py::ConditionCode — a fixed 8-value enum; every code
// is mapped here so nothing silently falls through unclassified. Moved
// here (from RiskList, which now imports it) so other simple-first cards
// can share the same plain-language sentence for the same code rather
// than writing a second one.
export type Severity = "Critical" | "High" | "Medium" | "Low";

export const CONDITION_SEVERITY: Record<ConditionCode, Severity> = {
  GATE_FAILED: "Critical",
  WRONG_BUILDING_RETURNED: "High",
  HIGH_SHADING: "High",
  SHADING_DATA_UNAVAILABLE: "Medium",
  MISSING_GEOMETRY_CONFIDENCE: "Medium",
  MISSING_CAPACITY_DATA: "Medium",
  NO_SOLAR_API_COVERAGE: "Medium",
  GATE_PENDING: "Medium",
};

export const CONDITION_LABEL: Record<ConditionCode, string> = {
  GATE_FAILED: "A hard installation requirement was not met",
  WRONG_BUILDING_RETURNED: "Possible building-match mismatch",
  HIGH_SHADING: "High shading detected",
  SHADING_DATA_UNAVAILABLE: "Shading could not be assessed",
  MISSING_GEOMETRY_CONFIDENCE: "Boundary confidence is low",
  MISSING_CAPACITY_DATA: "Some sizing data is missing",
  NO_SOLAR_API_COVERAGE: "No automatic roof data at this location",
  GATE_PENDING: "Awaiting confirmation",
};

/** Collapses the existing 4-tier severity into the doc's 3-tone
 *  GOOD/CHECK-NEEDED/NOT-SUITABLE language — Low reads as "nothing
 *  urgent" (good), Medium as "worth a look" (check), Critical/High as
 *  "needs attention" (bad). The underlying severity/detail text is
 *  unchanged; this only picks which icon/color a risk item gets. */
export function severityTone(severity: Severity): StatusTone {
  if (severity === "Critical" || severity === "High") return "bad";
  if (severity === "Medium") return "check";
  return "good";
}

/** Fallback for any snake_case internal label with no dedicated
 *  plain-language entry (e.g. a ceiling-ledger constraint name not in
 *  CONSTRAINT_LABEL, or a condition code somehow missing above) — turns
 *  `evacuation_headroom` into `Evacuation headroom` rather than leaking
 *  the raw internal string to a customer. */
export function humanizeLabel(label: string): string {
  const spaced = label.replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
