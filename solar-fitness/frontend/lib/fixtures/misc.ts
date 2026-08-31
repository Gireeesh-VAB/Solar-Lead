import type {
  CalibrationProposal,
  CompositeSite,
  HistoryEvent,
  ImportJob,
  JurisdictionConstraintPack,
  ModelVersionProposal,
} from "@/lib/types";
import { MOCK_SITES } from "@/lib/fixtures/sites";

export const MOCK_IMPORT_JOBS: ImportJob[] = [
  {
    id: "JOB-2201",
    fileName: "telangana_rooftop_batch3.csv",
    status: "running",
    totalRows: 220,
    processedRows: 138,
    errorRows: 6,
    createdAt: new Date(Date.now() - 12 * 60000).toISOString(),
    createdBy: "vabinformaticshyd@gmail.com",
    rows: Array.from({ length: 30 }, (_, i) => ({
      row: i + 2,
      identifier: `Site row ${i + 2}`,
      status: i % 11 === 0 ? "error" : i % 7 === 0 ? "warning" : "success",
      message:
        i % 11 === 0
          ? "Missing latitude/longitude — geocoding from address failed."
          : i % 7 === 0
          ? "Address matched with low confidence; please review."
          : undefined,
    })),
  },
  {
    id: "JOB-2198",
    fileName: "ap_floating_reservoirs.xlsx",
    status: "partial",
    totalRows: 18,
    processedRows: 18,
    errorRows: 3,
    createdAt: new Date(Date.now() - 3 * 86400000).toISOString(),
    createdBy: "vabinformaticshyd@gmail.com",
    rows: Array.from({ length: 18 }, (_, i) => ({
      row: i + 2,
      identifier: `Reservoir block ${i + 1}`,
      status: [3, 9, 14].includes(i) ? "error" : "success",
      message: [3, 9, 14].includes(i) ? "Waterbody polygon not found in registry." : undefined,
    })),
  },
  {
    id: "JOB-2150",
    fileName: "gujarat_ci_sites_q2.csv",
    status: "complete",
    totalRows: 96,
    processedRows: 96,
    errorRows: 0,
    createdAt: new Date(Date.now() - 14 * 86400000).toISOString(),
    createdBy: "ops-import@vabinformatics.com",
    rows: Array.from({ length: 20 }, (_, i) => ({
      row: i + 2,
      identifier: `CI site ${i + 1}`,
      status: "success",
    })),
  },
];

export const MOCK_HISTORY: Record<string, HistoryEvent[]> = Object.fromEntries(
  MOCK_SITES.slice(0, 20).map((site) => [
    site.id,
    [
      {
        id: `${site.id}-h1`,
        siteId: site.id,
        actor: "system@fitness-engine",
        timestamp: site.createdAt,
        kind: "created" as const,
        summary: "Site record created from bulk import.",
      },
      {
        id: `${site.id}-h2`,
        siteId: site.id,
        actor: "priya.rao@vabinformatics.com",
        timestamp: new Date(new Date(site.createdAt).getTime() + 2 * 86400000).toISOString(),
        kind: "boundary_edit" as const,
        summary: "Roof boundary adjusted after AI (VIS) suggestion review.",
        supersededFields: [{ field: "boundary_area_sqm", oldValue: "412", newValue: "455" }],
      },
      {
        id: `${site.id}-h3`,
        siteId: site.id,
        actor: "system@fitness-engine",
        timestamp: site.latestAssessment?.assessedAt ?? site.updatedAt,
        kind: "assessment" as const,
        summary: `Assessment run produced verdict ${site.latestAssessment?.verdict} at ${site.latestAssessment?.capacityKwp} kWp.`,
        supersededFields: [{ field: "capacity_kwp", oldValue: "38.2", newValue: String(site.latestAssessment?.capacityKwp ?? "-") }],
      },
      {
        id: `${site.id}-h4`,
        siteId: site.id,
        actor: "field.surveyor@vabinformatics.com",
        timestamp: site.updatedAt,
        kind: "field_survey" as const,
        summary: "Field survey uploaded; structural rating confirmed.",
      },
    ],
  ])
);

export const MOCK_COMPOSITES: CompositeSite[] = [
  {
    id: "CMP-01",
    name: "Rangareddy Feeder-14 Composite",
    feederOrDt: "Feeder-14 / DT-221",
    memberSiteIds: MOCK_SITES.slice(0, 5).map((s) => s.id),
    aggregateCapacityKwp: MOCK_SITES.slice(0, 5).reduce((a, s) => a + (s.latestAssessment?.capacityKwp ?? 0), 0),
    createdAt: new Date(Date.now() - 20 * 86400000).toISOString(),
  },
  {
    id: "CMP-02",
    name: "Guntur DT-88 Composite",
    feederOrDt: "Feeder-6 / DT-88",
    memberSiteIds: MOCK_SITES.slice(10, 14).map((s) => s.id),
    aggregateCapacityKwp: MOCK_SITES.slice(10, 14).reduce((a, s) => a + (s.latestAssessment?.capacityKwp ?? 0), 0),
    createdAt: new Date(Date.now() - 8 * 86400000).toISOString(),
  },
];

export const MOCK_CALIBRATION: CalibrationProposal[] = [
  {
    id: "CAL-501",
    jurisdiction: "Telangana — Rangareddy",
    metric: "Usable roof area factor",
    remoteValue: 0.82,
    measuredValue: 0.74,
    variancePct: -9.8,
    sampleSize: 46,
    proposedAdjustment: "Reduce remote usable-area factor from 0.82 to 0.75 for pitched-roof residential sites in this district.",
    status: "pending_approval",
    proposedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
    proposedBy: "calibration-engine",
  },
  {
    id: "CAL-497",
    jurisdiction: "Gujarat — Ahmedabad",
    metric: "Generation P50 (kWh/kWp/yr)",
    remoteValue: 1512,
    measuredValue: 1487,
    variancePct: -1.7,
    sampleSize: 112,
    proposedAdjustment: "No adjustment recommended — variance within tolerance band.",
    status: "approved",
    proposedAt: new Date(Date.now() - 30 * 86400000).toISOString(),
    proposedBy: "calibration-engine",
  },
  {
    id: "CAL-489",
    jurisdiction: "Andhra Pradesh — Krishna",
    metric: "Floating array surface-coverage cap",
    remoteValue: 0.3,
    measuredValue: 0.24,
    variancePct: -20.0,
    sampleSize: 9,
    proposedAdjustment: "Tighten default surface-coverage assumption from 30% to 25% pending regulator confirmation.",
    status: "pending_approval",
    proposedAt: new Date(Date.now() - 5 * 86400000).toISOString(),
    proposedBy: "calibration-engine",
  },
];

export const MOCK_MODEL_VERSIONS: ModelVersionProposal[] = [
  {
    id: "MDL-2.4.0-rc1",
    modelName: "fitness-core",
    version: "2.4.0-rc1",
    status: "proposed",
    metrics: [
      { label: "Boundary IoU (val)", value: "0.913" },
      { label: "Capacity MAE", value: "4.2 kWp" },
      { label: "Verdict agreement vs. field", value: "91.4%" },
    ],
    proposedAt: new Date(Date.now() - 3 * 86400000).toISOString(),
    proposedBy: "ml-platform@vabinformatics.com",
    changelog: "Retrained boundary segmentation on 2,300 new field-verified rooftops; improved floating-array shoreline masking.",
  },
  {
    id: "MDL-2.3.1",
    modelName: "fitness-core",
    version: "2.3.1",
    status: "active",
    metrics: [
      { label: "Boundary IoU (val)", value: "0.897" },
      { label: "Capacity MAE", value: "4.9 kWp" },
      { label: "Verdict agreement vs. field", value: "89.1%" },
    ],
    proposedAt: new Date(Date.now() - 60 * 86400000).toISOString(),
    proposedBy: "ml-platform@vabinformatics.com",
    changelog: "Current production model. Adds CONDITIONAL verdict calibration for DISCOM net-metering ceilings.",
  },
  {
    id: "MDL-2.2.6",
    modelName: "fitness-core",
    version: "2.2.6",
    status: "rejected",
    metrics: [
      { label: "Boundary IoU (val)", value: "0.861" },
      { label: "Capacity MAE", value: "6.7 kWp" },
      { label: "Verdict agreement vs. field", value: "84.0%" },
    ],
    proposedAt: new Date(Date.now() - 95 * 86400000).toISOString(),
    proposedBy: "ml-platform@vabinformatics.com",
    changelog: "Rejected: regressed on floating-array capacity estimates in Krishna district pilot.",
  },
];

export const MOCK_JURISDICTIONS: JurisdictionConstraintPack[] = [
  {
    id: "JUR-TS",
    jurisdiction: "Telangana",
    state: "Telangana",
    version: "2026.03",
    updatedAt: new Date(Date.now() - 40 * 86400000).toISOString(),
    rules: [
      { name: "Net-metering ceiling", kind: "regulatory", description: "Residential net-metering capped at 1x sanctioned load, max 10 kWp." },
      { name: "Structural safety certificate", kind: "physical", description: "Mandatory structural certificate for roofs older than 15 years." },
      { name: "Group captive minimum", kind: "commercial", description: "Group captive structures require minimum 26% ownership stake." },
    ],
  },
  {
    id: "JUR-GJ",
    jurisdiction: "Gujarat",
    state: "Gujarat",
    version: "2026.01",
    updatedAt: new Date(Date.now() - 70 * 86400000).toISOString(),
    rules: [
      { name: "Net-metering ceiling", kind: "regulatory", description: "Net-metering capped at 100% of sanctioned load for C&I connections." },
      { name: "Floating array coverage cap", kind: "regulatory", description: "Floating solar limited to 30% of reservoir surface area." },
    ],
  },
  {
    id: "JUR-KA",
    jurisdiction: "Karnataka",
    state: "Karnataka",
    version: "2025.11",
    updatedAt: new Date(Date.now() - 110 * 86400000).toISOString(),
    rules: [
      { name: "Net-metering ceiling", kind: "regulatory", description: "Gross metering mandatory above 150 kWp." },
      { name: "Heritage zoning exclusion", kind: "regulatory", description: "No rooftop structural modification permitted in listed heritage precincts." },
    ],
  },
];
