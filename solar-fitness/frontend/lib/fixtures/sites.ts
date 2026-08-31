import type {
  Assessment,
  BindingConstraint,
  CeilingLedgerEntry,
  ConfidenceTier,
  Site,
  SiteType,
  Verdict,
} from "@/lib/types";

// Deterministic seeded PRNG so fixtures are stable across reloads/builds.
function mulberry32(seed: number) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(42);
const pick = <T,>(arr: T[]): T => arr[Math.floor(rand() * arr.length)];
const randInt = (min: number, max: number) => Math.floor(rand() * (max - min + 1)) + min;
const randFloat = (min: number, max: number, dp = 2) =>
  Number((rand() * (max - min) + min).toFixed(dp));

const DISTRICTS: { district: string; state: string; lat: number; lng: number }[] = [
  { district: "Rangareddy", state: "Telangana", lat: 17.2, lng: 78.3 },
  { district: "Medchal-Malkajgiri", state: "Telangana", lat: 17.5, lng: 78.5 },
  { district: "Krishna", state: "Andhra Pradesh", lat: 16.2, lng: 80.6 },
  { district: "Guntur", state: "Andhra Pradesh", lat: 16.3, lng: 80.4 },
  { district: "Pune", state: "Maharashtra", lat: 18.5, lng: 73.8 },
  { district: "Nashik", state: "Maharashtra", lat: 20.0, lng: 73.8 },
  { district: "Ahmedabad", state: "Gujarat", lat: 23.0, lng: 72.6 },
  { district: "Surat", state: "Gujarat", lat: 21.2, lng: 72.8 },
  { district: "Jaipur", state: "Rajasthan", lat: 26.9, lng: 75.8 },
  { district: "Jodhpur", state: "Rajasthan", lat: 26.3, lng: 73.0 },
  { district: "Bengaluru Urban", state: "Karnataka", lat: 12.97, lng: 77.6 },
  { district: "Mysuru", state: "Karnataka", lat: 12.3, lng: 76.6 },
  { district: "Coimbatore", state: "Tamil Nadu", lat: 11.0, lng: 76.9 },
  { district: "Madurai", state: "Tamil Nadu", lat: 9.9, lng: 78.1 },
  { district: "Indore", state: "Madhya Pradesh", lat: 22.7, lng: 75.8 },
  { district: "Bhopal", state: "Madhya Pradesh", lat: 23.25, lng: 77.4 },
  { district: "Nagpur", state: "Maharashtra", lat: 21.1, lng: 79.1 },
  { district: "Lucknow", state: "Uttar Pradesh", lat: 26.8, lng: 80.9 },
  { district: "Varanasi", state: "Uttar Pradesh", lat: 25.3, lng: 83.0 },
  { district: "Patna", state: "Bihar", lat: 25.6, lng: 85.1 },
];

const SITE_TYPES: SiteType[] = [
  "ROOFTOP_GOVT",
  "ROOFTOP_RESIDENTIAL",
  "ROOFTOP_CI",
  "FLOATING",
];

const GOVT_NAMES = [
  "Zilla Parishad High School",
  "District Collectorate Annexe",
  "Government ITI Campus",
  "Primary Health Centre",
  "Municipal Corporation Office",
  "Government Degree College",
  "Taluk Panchayat Office",
  "District Court Complex",
  "Government Polytechnic",
  "Rural Water Works Pump House",
];
const RESIDENTIAL_NAMES = [
  "Sri Ram Nivas",
  "Lakshmi Residency",
  "Green Valley Homes",
  "Anand Bhavan",
  "Sunrise Apartments",
  "Krishna Kutir",
  "Vijay Nagar Villa",
  "Shanti Sadan",
];
const CI_NAMES = [
  "Sundar Textiles Pvt Ltd",
  "Bharat Auto Components",
  "Nandi Cold Storage",
  "Sri Balaji Rice Mill",
  "Deccan Warehousing Hub",
  "Ganesh Agro Processing Unit",
  "Krishna Valley Mall",
  "Orient Packaging Industries",
  "Sai Precision Tools",
  "Nova Pharma Formulations",
];
const FLOATING_NAMES = [
  "Nagarjuna Sagar Backwater Reservoir",
  "Osman Sagar Lake",
  "Tungabhadra Irrigation Tank",
  "Mettur Dam Reservoir Cove",
  "Ujjani Dam Backwater",
  "Himayat Sagar Reservoir",
];

function nameFor(type: SiteType, i: number): string {
  switch (type) {
    case "ROOFTOP_GOVT":
      return `${pick(GOVT_NAMES)} — ${i}`;
    case "ROOFTOP_RESIDENTIAL":
      return `${pick(RESIDENTIAL_NAMES)}, Site ${i}`;
    case "ROOFTOP_CI":
      return `${pick(CI_NAMES)}`;
    case "FLOATING":
      return `${pick(FLOATING_NAMES)} — Block ${i}`;
  }
}

const VERDICTS: Verdict[] = [
  "SUITABLE",
  "SUITABLE",
  "SUITABLE",
  "SUITABLE_SUBJECT_TO_SURVEY",
  "SUITABLE_SUBJECT_TO_SURVEY",
  "CONDITIONAL",
  "CONDITIONAL",
  "INSUFFICIENT_DATA",
  "NOT_SUITABLE",
];
const CONFIDENCE: ConfidenceTier[] = ["High", "High", "Medium", "Medium", "Low"];

const CONSTRAINT_LIBRARY: Record<Verdict, BindingConstraint[]> = {
  SUITABLE: [
    { name: "Available roof area", reason: "Usable shadow-free area supports full requested capacity.", kind: "physical" },
    { name: "Sanctioned load headroom", reason: "Feeder headroom comfortably exceeds proposed DC capacity.", kind: "regulatory" },
  ],
  SUITABLE_SUBJECT_TO_SURVEY: [
    { name: "Roof structural rating", reason: "Desk assessment assumes standard RCC load rating — needs field structural survey to confirm.", kind: "physical" },
    { name: "Shading from adjacent structure", reason: "Nearby structure height estimated from imagery only; field verification recommended.", kind: "physical" },
  ],
  CONDITIONAL: [
    { name: "DISCOM net-metering ceiling", reason: "Capacity exceeds current net-metering ceiling; feasible only with group captive or open-access structuring.", kind: "regulatory" },
    { name: "Sanctioned connected load", reason: "Proposed DC capacity exceeds 1x sanctioned load; requires load enhancement application.", kind: "commercial" },
  ],
  INSUFFICIENT_DATA: [
    { name: "Roof imagery resolution", reason: "Available satellite imagery predates recent construction; boundary confidence too low to size capacity.", kind: "physical" },
    { name: "Ownership/title records", reason: "Site ownership records not yet linked; commercial feasibility cannot be confirmed.", kind: "commercial" },
  ],
  NOT_SUITABLE: [
    { name: "Heritage/no-build zoning", reason: "Site falls within a heritage conservation zone that prohibits rooftop structural additions.", kind: "regulatory" },
    { name: "Structural condition", reason: "Roof shows visible structural distress in imagery; unsafe for panel loading without major remediation.", kind: "physical" },
  ],
};

function ceilingLedgerFor(type: SiteType, capacityKwp: number, binding: BindingConstraint | null): CeilingLedgerEntry[] {
  const base: CeilingLedgerEntry[] = [
    { label: "Available area ceiling", kwp: Number((capacityKwp * randFloat(1.05, 1.4)).toFixed(1)), kind: "physical" },
    { label: "Sanctioned load ceiling", kwp: Number((capacityKwp * randFloat(0.9, 1.6)).toFixed(1)), kind: "regulatory" },
    { label: "DISCOM net-metering ceiling", kwp: Number((capacityKwp * randFloat(0.85, 1.5)).toFixed(1)), kind: "regulatory" },
    { label: "Commercial viability ceiling", kwp: Number((capacityKwp * randFloat(1.0, 1.8)).toFixed(1)), kind: "commercial" },
  ];
  if (type === "FLOATING") {
    base.push({ label: "Water body surface-coverage cap (30%)", kwp: Number((capacityKwp * randFloat(1.0, 1.3)).toFixed(1)), kind: "regulatory" });
  }
  return base
    .map((e) => ({ ...e, isBinding: binding ? e.label.toLowerCase().includes(binding.name.split(" ")[0].toLowerCase()) : false }))
    .sort((a, b) => a.kwp - b.kwp);
}

function buildAssessment(site: Omit<Site, "latestAssessment">, index: number): Assessment {
  const verdict = pick(VERDICTS);
  const confidence: ConfidenceTier = verdict === "INSUFFICIENT_DATA" ? "N/A" : pick(CONFIDENCE);
  const capacityBase =
    site.siteType === "ROOFTOP_RESIDENTIAL"
      ? randFloat(2, 10, 1)
      : site.siteType === "ROOFTOP_GOVT"
      ? randFloat(15, 120, 1)
      : site.siteType === "ROOFTOP_CI"
      ? randFloat(50, 500, 1)
      : randFloat(500, 4000, 1);
  const capacityKwp = verdict === "NOT_SUITABLE" ? 0 : verdict === "INSUFFICIENT_DATA" ? 0 : capacityBase;
  const bindingPool = CONSTRAINT_LIBRARY[verdict];
  const bindingConstraint = verdict === "SUITABLE" && rand() > 0.5 ? null : pick(bindingPool);
  const cacheHit = rand() > 0.78;
  const isPanorama = site.siteType !== "FLOATING" && rand() > 0.55;

  const reasonsPool: Record<Verdict, string[]> = {
    SUITABLE: [
      "Usable roof/site area exceeds minimum threshold for the requested capacity.",
      "No structural, shading, or regulatory blockers identified in desk review.",
      "Sanctioned load and net-metering headroom both support full capacity.",
    ],
    SUITABLE_SUBJECT_TO_SURVEY: [
      "Desk assessment is positive but relies on assumptions that need field confirmation.",
      "Roof structural rating not verified on-site; imagery-based estimate used.",
      "Recommend a field structural and shading survey before final sign-off.",
    ],
    CONDITIONAL: [
      "Site is technically suitable but commercial/regulatory structuring is required.",
      "Capacity is capped below the physical ceiling by regulatory or commercial limits.",
      "Feasible with load enhancement or alternate commercial structuring.",
    ],
    INSUFFICIENT_DATA: [
      "Available imagery/records are inadequate to produce a confident capacity figure.",
      "No result should be treated as a negative signal — this is a data-gap, not a rejection.",
      "Recommend field data capture or updated satellite pass to proceed.",
    ],
    NOT_SUITABLE: [
      "A hard physical or regulatory blocker rules out installation at this site.",
      "No commercial structuring can overcome the identified constraint.",
    ],
  };

  return {
    id: `AS-${index.toString().padStart(5, "0")}`,
    siteId: site.id,
    verdict,
    capacityKwp,
    confidence,
    bindingConstraint,
    reasons: reasonsPool[verdict],
    ceilingLedger: verdict === "INSUFFICIENT_DATA" ? [] : ceilingLedgerFor(site.siteType, capacityKwp || 10, bindingConstraint),
    visionRefinement:
      rand() > 0.5
        ? {
            applied: true,
            deltaKwp: Number(randFloat(-8, 12, 1)),
            note: "Vision (VIS) module refined roof boundary from satellite imagery, adjusting usable area.",
          }
        : undefined,
    panoramaUrl: isPanorama ? `/panoramas/mock-${(index % 6) + 1}.jpg` : null,
    mlSuitabilityScore: verdict === "INSUFFICIENT_DATA" ? null : Number(randFloat(0.42, 0.97, 2)),
    generation:
      verdict === "NOT_SUITABLE" || verdict === "INSUFFICIENT_DATA"
        ? undefined
        : {
            p50AnnualKwh: Math.round(capacityKwp * randFloat(1350, 1550)),
            p90AnnualKwh: Math.round(capacityKwp * randFloat(1200, 1350)),
          },
    cache: {
      cacheHit,
      reusedFromAnalysisId: cacheHit ? `AS-${(index - randInt(3, 40)).toString().padStart(5, "0")}` : undefined,
      originalDate: cacheHit
        ? new Date(Date.now() - randInt(20, 400) * 86400000).toISOString()
        : undefined,
    },
    assessedAt: new Date(Date.now() - randInt(0, 90) * 86400000).toISOString(),
    modelVersion: pick(["fitness-core-v2.3.1", "fitness-core-v2.4.0-rc1", "fitness-core-v2.2.6"]),
  };
}

function buildSite(index: number): Site {
  const type = SITE_TYPES[index % SITE_TYPES.length] === "FLOATING" && rand() > 0.25 ? pick(SITE_TYPES.filter((t) => t !== "FLOATING")) : SITE_TYPES[index % SITE_TYPES.length];
  const geo = pick(DISTRICTS);
  const base: Omit<Site, "latestAssessment"> = {
    id: `ST-${(1000 + index).toString()}`,
    name: nameFor(type, index),
    siteType: type,
    address: `${randInt(1, 200)}, ${pick(["Main Road", "Ring Road", "Station Road", "MG Road", "Industrial Area", "Canal Bund Road"])}, ${geo.district}`,
    district: geo.district,
    state: geo.state,
    location: {
      lat: Number((geo.lat + randFloat(-0.35, 0.35, 3)).toFixed(5)),
      lng: Number((geo.lng + randFloat(-0.35, 0.35, 3)).toFixed(5)),
    },
    createdAt: new Date(Date.now() - randInt(10, 260) * 86400000).toISOString(),
    updatedAt: new Date(Date.now() - randInt(0, 30) * 86400000).toISOString(),
    usnStatus:
      type === "ROOFTOP_RESIDENTIAL" || type === "ROOFTOP_CI"
        ? pick(["not_started", "pending_confirmation", "confirmed", "confirmed"])
        : undefined,
    usn:
      type === "ROOFTOP_RESIDENTIAL" || type === "ROOFTOP_CI"
        ? rand() > 0.4
          ? `USN${randInt(100000000, 999999999)}`
          : null
        : null,
    tags: [pick(["priority", "shortlisted", "pilot-batch", "revisit", "field-verified"]), ...(rand() > 0.7 ? [pick(["escalated", "high-value"])] : [])],
  };
  return { ...base, latestAssessment: buildAssessment(base, index) };
}

export const SITE_COUNT = 54;
export const MOCK_SITES: Site[] = Array.from({ length: SITE_COUNT }, (_, i) => buildSite(i + 1));

export function getSiteById(id: string): Site | undefined {
  return MOCK_SITES.find((s) => s.id === id);
}
