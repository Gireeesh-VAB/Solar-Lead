// -----------------------------------------------------------------------------
// Fixtures for the consumer-facing Customer portal.
//
// A "check" is conceptually the same object as a Site with a latestAssessment
// attached (see lib/types.ts) — this file just reuses that shape rather than
// inventing a parallel model, and hand-authors a small set of plain-language
// binding-constraint reasons suited to a non-technical homeowner audience
// (the enterprise CONSTRAINT_LIBRARY in lib/fixtures/sites.ts is written for
// analysts and leans on jargon that doesn't belong here).
// -----------------------------------------------------------------------------

import type { Assessment, BindingConstraint, Site, Verdict } from "@/lib/types";

export interface CustomerProfile {
  name: string;
  email: string;
  phone: string;
  notifyOnComplete: boolean;
}

export const MOCK_CUSTOMER: CustomerProfile = {
  name: "Priya Raman",
  email: "priya.raman@example.com",
  phone: "+91 98765 43210",
  notifyOnComplete: true,
};

// Plain-language "what this means" copy per verdict — used on the result
// screen. Deliberately avoids jargon (no "GEO-04", no "ceiling").
export const VERDICT_EXPLAINER: Record<Verdict, string> = {
  SUITABLE:
    "Your location looks like a strong fit for solar. There's enough usable space and no blockers showed up in our checks.",
  SUITABLE_SUBJECT_TO_SURVEY:
    "Your location looks promising. Before anything is finalised, someone should visit in person to confirm a couple of details we can't fully see from imagery alone.",
  CONDITIONAL:
    "Solar can work here, but it will need a bit of extra paperwork or a different connection arrangement to go ahead.",
  INSUFFICIENT_DATA:
    "We don't have quite enough information yet to give you a confident answer — that's not a bad sign, it just means we need a clearer look. Try again shortly, or an on-site visit can settle it.",
  NOT_SUITABLE:
    "Based on what we found, this exact spot isn't a good match for solar right now. That's useful to know early, and it doesn't reflect on you or the property overall.",
};

const PLAIN_CONSTRAINTS: Record<Verdict, BindingConstraint | null> = {
  SUITABLE: null,
  SUITABLE_SUBJECT_TO_SURVEY: {
    name: "Roof check needed",
    reason: "Everything we can see points to a good fit, but we'd like someone to confirm the roof in person before locking in the details.",
    kind: "physical",
  },
  CONDITIONAL: {
    name: "Connection paperwork",
    reason: "The size of system this location can support is a little larger than a standard home connection allows, so a simple upgrade request will be needed first.",
    kind: "regulatory",
  },
  INSUFFICIENT_DATA: {
    name: "Clearer imagery needed",
    reason: "The images we have of this location aren't recent or sharp enough to size a system with confidence yet.",
    kind: "physical",
  },
  NOT_SUITABLE: {
    name: "Space and shading",
    reason: "There isn't enough clear, unshaded space at this exact location to fit a workable solar system.",
    kind: "physical",
  },
};

const PLAIN_REASONS: Record<Verdict, string[]> = {
  SUITABLE: ["Enough clear space for a solar system.", "No blockers found nearby."],
  SUITABLE_SUBJECT_TO_SURVEY: ["Looks good from imagery.", "A quick in-person check will confirm it."],
  CONDITIONAL: ["The location can support solar.", "A connection upgrade step is needed first."],
  INSUFFICIENT_DATA: ["The available imagery isn't clear enough yet.", "This is a data gap, not a rejection."],
  NOT_SUITABLE: ["Not enough usable space at this exact spot.", "Shading or layout rules it out for now."],
};

function buildCheckAssessment(checkId: string, verdict: Verdict, capacityKwp: number, daysAgo: number): Assessment {
  return {
    id: `CHKAS-${checkId}`,
    siteId: checkId,
    verdict,
    capacityKwp,
    confidence: verdict === "INSUFFICIENT_DATA" ? "N/A" : verdict === "SUITABLE" ? "High" : "Medium",
    bindingConstraint: PLAIN_CONSTRAINTS[verdict],
    reasons: PLAIN_REASONS[verdict],
    ceilingLedger: [],
    panoramaUrl: null,
    mlSuitabilityScore: verdict === "INSUFFICIENT_DATA" ? null : Number((0.6 + Math.random() * 0.35).toFixed(2)),
    generation:
      verdict === "NOT_SUITABLE" || verdict === "INSUFFICIENT_DATA"
        ? undefined
        : { p50AnnualKwh: Math.round(capacityKwp * 1450), p90AnnualKwh: Math.round(capacityKwp * 1280) },
    cache: { cacheHit: false },
    assessedAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
    modelVersion: "fitness-core-v2.4.0",
  };
}

function buildCheck(
  id: string,
  name: string,
  address: string,
  lat: number,
  lng: number,
  verdict: Verdict,
  capacityKwp: number,
  daysAgo: number
): Site {
  return {
    id,
    name,
    siteType: "ROOFTOP_RESIDENTIAL",
    address,
    district: "Hyderabad",
    state: "Telangana",
    location: { lat, lng },
    createdAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - daysAgo * 86400000).toISOString(),
    latestAssessment: buildCheckAssessment(id, verdict, capacityKwp, daysAgo),
    tags: [],
  };
}

// A handful of past checks tied to the demo homeowner, with varied verdicts.
export const MOCK_CHECKS: Site[] = [
  buildCheck("CHK-1001", "Home — Jubilee Hills", "12-2-823, Road No. 5, Jubilee Hills", 17.4239, 78.4738, "SUITABLE", 4.5, 3),
  buildCheck("CHK-1002", "Weekend home — Shamirpet", "Plot 44, Lakeview Colony, Shamirpet", 17.5806, 78.5866, "SUITABLE_SUBJECT_TO_SURVEY", 5.2, 12),
  buildCheck("CHK-1003", "Parents' house — Kukatpally", "8-1-284, KPHB Colony, Kukatpally", 17.4849, 78.3915, "CONDITIONAL", 6.8, 25),
  buildCheck("CHK-1004", "Rental — Gachibowli", "Flat 302, Silver Oaks, Gachibowli", 17.4401, 78.3489, "INSUFFICIENT_DATA", 0, 41),
];

export function getCheckById(id: string): Site | undefined {
  return MOCK_CHECKS.find((c) => c.id === id);
}
