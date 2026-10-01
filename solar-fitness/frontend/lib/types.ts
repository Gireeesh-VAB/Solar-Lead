// Core domain types for the Solar Site Fitness & Capacity Engine frontend.
// These mirror the shapes the future FastAPI backend is expected to return.

export type Verdict =
  | "SUITABLE"
  | "SUITABLE_SUBJECT_TO_SURVEY"
  | "CONDITIONAL"
  | "INSUFFICIENT_DATA"
  | "NOT_SUITABLE";

export type ConfidenceTier = "High" | "Medium" | "Low" | "N/A";

export type SiteType =
  | "ROOFTOP_GOVT"
  | "ROOFTOP_RESIDENTIAL"
  | "ROOFTOP_CI"
  | "FLOATING";

export type ConstraintKind = "physical" | "regulatory" | "commercial";

export interface BindingConstraint {
  name: string;
  reason: string;
  kind: ConstraintKind;
}

export type ConstraintStatus = "ok" | "estimated" | "insufficient_data" | "not_applicable";

export interface CeilingLedgerEntry {
  label: string;
  /** Null when the constraint could not be evaluated. Deliberately NOT
   *  defaulted to 0 — "we haven't checked this" and "this limits you to
   *  nothing" are opposite claims, and a zero here reads as the second. */
  kwp: number | null;
  kind: ConstraintKind;
  status: ConstraintStatus;
  note?: string;
  isBinding?: boolean;
}

export interface CacheProvenance {
  cacheHit: boolean;
  reusedFromAnalysisId?: string;
  originalDate?: string;
}

// Matches routers/assessments.py::GenerationEstimateOut — the real
// output of engine/generation.py::estimate_generation_kwh(), previously
// computed on every assessment and silently discarded. p50/p90 are
// always null today (GEN-06, deferred in the engine itself).
export interface GenerationEstimate {
  estimatedKwhPerYear: number | null;
  specificYieldKwhPerKwp: number | null;
  performanceRatio: number | null;
  method: string;
  methodNotes: string;
  p50KwhPerYear?: number | null;
  p90KwhPerYear?: number | null;
  pvgisAnnualKwh?: number | null;
  pvgisMonthlyKwh?: number[] | null;
}

// engine/fitness.py::FitnessResult.components — the per-factor breakdown
// behind the single blended `score`. Each is null when that factor's
// input was unavailable (never a fabricated number standing in for it).
export interface ScoreComponents {
  capacityAdequacy?: number | null;
  constraintHeadroom?: number | null;
  geometryQuality?: number | null;
  shading?: number | null;
  generationYield?: number | null;
}

// engine/fitness.py::FitnessResult.confidence_components — the real
// per-factor breakdown behind `confidenceScore` (FIT-04). Each is null
// when that factor's input was unavailable (never a fabricated number
// standing in for it) — same discipline as ScoreComponents above.
export interface ConfidenceComponents {
  geometry?: number | null;
  imageryRecency?: number | null;
  constraintCompleteness?: number | null;
  gateResolution?: number | null;
  calibrationState?: number | null;
  ceilingDelta?: number | null;
}

// Matches routers/assessments.py::FinancialEstimateOut — engine/
// financials.py's own config-pack-driven cost/subsidy/payback ESTIMATE.
// Distinct from the admin-owned financialFeasibility (a real, negotiated
// quote) surfaced only in the admin app — this is the indicative figure
// shown before any real quote exists. Every field is null-safe: a site
// type outside the subsidy scheme gets subsidyApplicable=false and
// subsidyAmountInr=null (never a fabricated 0), and every
// generation-derived figure is null when no generation estimate exists.
export interface FinancialEstimate {
  panelCostInr: number | null;
  inverterCostInr: number | null;
  mountingStructureCostInr: number | null;
  electricalMaterialCostInr: number | null;
  installationCostInr: number | null;
  totalProjectCostInr: number | null;
  subsidyApplicable: boolean;
  subsidyCategory: string | null;
  subsidyAmountInr: number | null;
  /** FIN-01 subsidy explainability — engine/financials.py::
   *  _explain_subsidy()'s docstring. subsidySchemeMaxAmountInr is the
   *  scheme-wide maximum, shown even when this customer isn't eligible
   *  (never conflated with subsidyAmountInr, this customer's actual
   *  eligible figure). subsidyIneligibilityReason is set only when
   *  subsidyApplicable is false; subsidyExplanation is deterministic,
   *  template-generated sentences, empty when not applicable. */
  subsidySchemeName: string | null;
  subsidySchemeMaxAmountInr: number | null;
  subsidyRateInrPerKwp: number | null;
  subsidySchemeMaxCapacityKwp: number | null;
  subsidyCapacityConsideredKwp: number | null;
  subsidyIneligibilityReason: string | null;
  subsidyExplanation: string[];
  customerContributionInr: number | null;
  monthlySavingsInr: number | null;
  annualSavingsInr: number | null;
  paybackPeriodYears: number | null;
  tenYearSavingsInr: number | null;
  twentyYearSavingsInr: number | null;
  estimatedSystemLifetimeYears: number | null;
  methodNotes: string;
}

// FIN-02 — engine/financial_projection.py's year-by-year output. Built
// ON TOP of FinancialEstimate above (never recomputes capacity/
// generation/cost), fetched separately via getCheckFinancialProjection()
// since it's its own backend call, not part of the Assessment payload.
export interface FinancialProjectionYear {
  year: number;
  generationKwh: number;
  degradationFactor: number;
  tariffInrPerKwh: number;
  selfConsumptionKwh: number;
  exportKwh: number;
  selfConsumptionSavingsInr: number;
  exportRevenueInr: number;
  grossBenefitInr: number;
  maintenanceCostInr: number;
  otherCostInr: number;
  netBenefitInr: number;
  emiCostInr: number;
  netCashFlowInr: number;
  cumulativeSavingsInr: number;
  cumulativeCashFlowInr: number;
  remainingInvestmentInr: number;
  roiPct: number;
}

export interface FinancialHorizonSummary {
  horizonYears: number;
  totalGenerationKwh: number;
  totalGrossSavingsInr: number;
  totalCostsInr: number;
  totalNetSavingsInr: number;
  cumulativeRoiPct: number;
  investmentRecovered: boolean;
  profitAfterRecoveryInr: number;
}

export interface FinancialPayback {
  recovered: boolean;
  paybackYear: number | null;
  paybackYears: number | null;
  paybackMonths: number | null;
  amountRecoveredBeforePaybackInr: number;
}

export interface FinancingScenario {
  downPaymentInr: number;
  loanAmountInr: number;
  interestRatePct: number;
  tenureYears: number;
  monthlyEmiInr: number;
  totalInterestInr: number;
  totalPaymentInr: number;
  yearly: FinancialProjectionYear[];
  payback: FinancialPayback;
  horizons: FinancialHorizonSummary[];
}

// FIN-03 — the seasonal (summer/rainy/winter) companion to the year-wise
// figures above. Absent (null) only when there's neither a kWh reading
// nor a bill amount on file for this check.
export interface SeasonEstimate {
  monthlyKwh: number;
  months: number;
  annualKwh: number;
  /** Rainy is always true; summer/winter are true only when derived
   *  from a ₹ bill amount instead of a direct kWh reading. */
  estimated: boolean;
}

export interface SeasonalConsumption {
  seasons: Record<"summer" | "rainy" | "winter", SeasonEstimate>;
  annualKwh: number;
  averageMonthlyKwh: number;
  highestMonthlyKwh: number;
  lowestMonthlyKwh: number;
  source: "kwh_reading" | "bill_amount_estimate";
  basis: string;
}

// FIN-03 §6/§7/§8 — electricity-based sizing shown ALONGSIDE the roof's
// own resolved capacity (roofCapacityKwp), never in place of it.
// recommendedKwp is always min(electricityRequiredKwp, roofCapacityKwp).
export interface SolarRequirement {
  electricityRequiredKwp: number;
  roofCapacityKwp: number;
  recommendedKwp: number;
  coveragePct: number;
}

export interface SeasonFinancial {
  season: string;
  months: number;
  consumptionKwh: number;
  consumptionEstimated: boolean;
  generationKwh: number;
  selfConsumptionKwh: number;
  exportKwh: number;
  tariffInrPerKwh: number;
  selfConsumptionSavingsInr: number;
  exportRevenueInr: number;
  grossBenefitInr: number;
  maintenanceCostInr: number;
  netBenefitInr: number;
  emiCostInr: number;
  netBenefitAfterEmiInr: number;
}

export interface SeasonalFinancial {
  seasons: Record<"summer" | "rainy" | "winter", SeasonFinancial>;
  annualGenerationKwh: number;
  annualGrossBenefitInr: number;
  annualMaintenanceInr: number;
  annualNetBenefitInr: number;
  annualEmiInr: number;
  annualNetBenefitAfterEmiInr: number;
  generationShares: Record<"summer" | "rainy" | "winter", number>;
  generationShareSource: "pvgis_actual" | "configured_fallback";
}

export interface FinancialProjection {
  capacityKwp: number;
  initialInvestmentInr: number;
  systemLifetimeYears: number;
  degradationPctPerYear: number;
  tariffEscalationPctPerYear: number;
  selfConsumptionRatioYear1: number;
  selfConsumptionBasis: string;
  yearly: FinancialProjectionYear[];
  threeYearSummary: FinancialHorizonSummary;
  horizons: FinancialHorizonSummary[];
  payback: FinancialPayback;
  lifetimeRoiPct: number;
  financing: FinancingScenario | null;
  methodNotes: string;
  assumptionsVersion: number;
  electricityProfile: SeasonalConsumption | null;
  solarRequirement: SolarRequirement | null;
  seasonal: SeasonalFinancial | null;
}

export interface Assessment {
  id: string;
  siteId: string;
  verdict: Verdict;
  capacityKwp: number;
  confidence: ConfidenceTier;
  /** repositories/assessments.py::raise_enquiry() — "not_submitted"
   *  until the customer explicitly raises an enquiry (the check and the
   *  enquiry are deliberately separate stages), then "pending"/
   *  "approved"/"rejected" as an admin acts on it. "not_applicable" for
   *  a verdict that was never eligible. The customer-safe subset of
   *  admin's own review fields — no reviewer name, no vendor id. */
  reviewStatus?: "not_submitted" | "pending" | "approved" | "rejected" | "not_applicable";
  enquirySubmittedAt?: string | null;
  /** engine/fitness.py::score_fitness()'s own 0..1 figure, rescaled to
   *  0-100. Null exactly when verdict is INSUFFICIENT_DATA (FIT-03) —
   *  never a fabricated low score standing in for missing data. */
  score?: number | null;
  /** Same rescale-to-0-100 treatment for the raw confidence float,
   *  alongside the existing bucketed `confidence` tier above. */
  confidenceScore?: number | null;
  scoreComponents?: ScoreComponents;
  /** engine/fitness.py::FitnessResult.confidence_components — the real
   *  per-factor values blended into confidenceScore above. */
  confidenceComponents?: ConfidenceComponents;
  /** engine/fitness.py::_explain_confidence()'s deterministic, template-
   *  generated sentences: index 0 is always the overall summary, the
   *  rest are one sentence per factor, ordered by contribution. */
  confidenceExplanation?: string[];
  bindingConstraint: BindingConstraint | null;
  reasons: string[];
  /** Phase 6 — see routers/assessments.py / domain/assessment.py::
   *  ConditionCode's docstring. Structured, branch-able reasons a
   *  verdict landed where it did — additive alongside `reasons`
   *  (free-text sentences) and `bindingConstraint` (the single deciding
   *  one). Empty for an older assessment predating Phase 6. */
  conditions?: Condition[];
  ceilingLedger: CeilingLedgerEntry[];
  /** CON-04 context behind the recommendation. All optional — an older
   *  assessment predating this may not carry them. */
  usableAreaM2?: number | null;
  /** engine/area.py::boundary_area_m2() — the raw roof area before
   *  setback/exclusions. Paired with usableAreaM2 above for a real
   *  total/usable/non-usable breakdown. */
  totalAreaM2?: number | null;
  maxTechnicalKwp?: number | null;
  headroomKwp?: number | null;
  /** engine/panel_packing.py's own real layout — see ResultMap's
   *  useCheckSolarLayout for the map overlay. This raw form is carried
   *  on the assessment mainly so its presence/absence is inspectable
   *  without a second request. */
  panelLayout?: Record<string, unknown> | null;
  /** Building Insights' per-plane roof data (pitch/azimuth/area/sunshine
   *  per roof segment) — see routers/assessments.py::_pack_panel_layout().
   *  Carried the same way panelLayout is, for the same reason. Typed as
   *  an opaque blob here (not `RoofSegments` directly) because an older
   *  assessment predating Phase 3 has this as `null`/a differently-shaped
   *  value — use `parseRoofSegments()` to get a validated array. */
  roofSegments?: Record<string, unknown> | null;
  /** A coarse "the Solar API may have matched a neighbouring building"
   *  warning — see routers/assessments.py::_building_match_warning(). */
  boundaryWarning?: string | null;
  /** engine/fitness.py::STANDARD_LIMITATIONS — the authoritative
   *  pre-feasibility disclaimer that ships on every assessment. */
  limitations?: string | null;
  visionRefinement?: {
    applied: boolean;
    deltaKwp: number;
    note: string;
  };
  panoramaUrl?: string | null;
  mlSuitabilityScore?: number | null;
  generation?: GenerationEstimate;
  financialEstimate?: FinancialEstimate;
  cache: CacheProvenance;
  assessedAt: string;
  modelVersion: string;
}

// -----------------------------------------------------------------------------
// Phase 3's per-plane roof data — see routers/assessments.py::
// _pack_panel_layout()'s `roof_segments` construction for the exact
// source shape. `Assessment.roofSegments` carries this as an opaque
// blob (an older assessment may hold null or a stale shape); parse it
// through parseRoofSegments() rather than casting it directly.
// -----------------------------------------------------------------------------

export interface RoofSegment {
  segmentIndex: number;
  pitchDeg: number | null;
  azimuthDeg: number | null;
  areaM2: number | null;
  groundAreaM2: number | null;
  sunshineQuantiles: number[];
  planeHeightM: number | null;
  /** This plane's own share of the resolved usable roof — routers/
   *  assessments.py::_metric_polygon_to_wgs84_ring(). null when the
   *  segment had no boundingBox, no real overlap with the usable roof,
   *  or the intersection produced something other than a single
   *  Polygon (never a mis-drawn partial shape). */
  polygon: { lat: number; lng: number }[] | null;
}

function parsePolygonRing(raw: unknown): { lat: number; lng: number }[] | null {
  if (!Array.isArray(raw)) return null;
  const points = raw
    .filter((p): p is [number, number] => Array.isArray(p) && p.length === 2 && p.every((n) => typeof n === "number"))
    .map(([lng, lat]) => ({ lat, lng }));
  return points.length >= 3 ? points : null;
}

export function parseRoofSegments(raw: Assessment["roofSegments"]): RoofSegment[] {
  const segments = raw && Array.isArray((raw as { segments?: unknown }).segments)
    ? (raw as { segments: unknown[] }).segments
    : [];
  return segments
    .filter((s): s is Record<string, unknown> => typeof s === "object" && s !== null)
    .map((s) => ({
      segmentIndex: typeof s.segmentIndex === "number" ? s.segmentIndex : 0,
      pitchDeg: typeof s.pitchDeg === "number" ? s.pitchDeg : null,
      azimuthDeg: typeof s.azimuthDeg === "number" ? s.azimuthDeg : null,
      areaM2: typeof s.areaM2 === "number" ? s.areaM2 : null,
      groundAreaM2: typeof s.groundAreaM2 === "number" ? s.groundAreaM2 : null,
      sunshineQuantiles: Array.isArray(s.sunshineQuantiles)
        ? s.sunshineQuantiles.filter((q): q is number => typeof q === "number")
        : [],
      planeHeightM: typeof s.planeHeightM === "number" ? s.planeHeightM : null,
      polygon: parsePolygonRing(s.polygon),
    }));
}

/** Compass point for a azimuth in degrees (0 = north, 90 = east, ...) —
 *  matches how a homeowner actually thinks about "which way does my roof
 *  face", not a raw degree number. */
export function compassDirection(azimuthDeg: number): string {
  const points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const index = Math.round(((azimuthDeg % 360) + 360) % 360 / 22.5) % 16;
  return points[index];
}

// -----------------------------------------------------------------------------
// Phase 6 — domain/assessment.py::ConditionCode. Structured, branch-able
// reasons alongside the verdict — never a replacement for it (see
// Assessment.verdict, which stays the sole authoritative feasibility
// state per FIT-06).
// -----------------------------------------------------------------------------

export type ConditionCode =
  | "WRONG_BUILDING_RETURNED"
  | "NO_SOLAR_API_COVERAGE"
  | "HIGH_SHADING"
  | "SHADING_DATA_UNAVAILABLE"
  | "MISSING_CAPACITY_DATA"
  | "MISSING_GEOMETRY_CONFIDENCE"
  | "GATE_FAILED"
  | "GATE_PENDING";

export interface Condition {
  code: ConditionCode;
  message: string;
  detail?: string | null;
}

export interface GeoPoint {
  lat: number;
  lng: number;
}

export type RoofType =
  | "RCC_CONCRETE"
  | "METAL_SHEET"
  | "GI_SHEET"
  | "TILED"
  | "ASBESTOS_SHEET"
  | "GROUND_MOUNTED"
  | "TERRACE"
  | "OTHER";
export type RoofMaterial = "RCC" | "CONCRETE" | "METAL" | "TILE" | "SHEET" | "OTHER";
export type RoofSlope = "FLAT" | "LOW" | "MEDIUM" | "HIGH";
export type ConnectionType = "SINGLE_PHASE" | "THREE_PHASE";

export interface MonthlyConsumptionEntry {
  month: string; // "2026-01"
  unitsKwh: number;
}

export interface Site {
  id: string;
  name: string;
  siteType: SiteType;
  address: string;
  district: string;
  state: string;
  location: GeoPoint;
  boundary?: GeoPoint[];
  /** GEO-09 provenance for `boundary`. "solar_api" means it is Google's
   *  bounding RECTANGLE, not a traced roof outline. */
  geometrySource?: string | null;
  /** True when `boundary` is an approximate box rather than a traced
   *  roof. Derived server-side so the UI need not know the enum. */
  boundaryIsApproximate?: boolean;
  geometryConfidence?: number | null;
  /** providers/solar_api.py::MaskVectorization.competing_regions — real
   *  count of other candidate buildings the mask found near the pin,
   *  captured once at check-creation time. null means no mask lookup
   *  ran at all (not "found zero"); 0 means it ran and the pin's
   *  building was unambiguous. */
  competingBuildingsNearby?: number | null;
  /** Never hidden, even when LOW/MEDIUM — a customer reading a panel
   *  layout is entitled to know how current/detailed the underlying
   *  satellite imagery actually is. */
  imageryQuality?: string | null;
  imageryDate?: string | null;
  // SHADE-01/02 — domain/site.py::ShadingEstimate. All null when
  // shadingSource is "unavailable" (any non-solar_api geometry source
  // carries no shading data) — never a guessed shading figure.
  shadingScore?: number | null;
  sunshineHoursPerYear?: number | null;
  shadingSource?: string | null;
  /** OBS-04's real, applied exclusion polygons (setbacks + obstacles
   *  already subtracted from the usable area) — one ring per polygon,
   *  same convention as `boundary` above. Null when the site has none. */
  exclusions?: GeoPoint[][] | null;
  createdAt: string;
  updatedAt: string;
  latestAssessment: Assessment | null;
  usnStatus?: "not_started" | "pending_confirmation" | "confirmed";
  usn?: string | null;
  tags: string[];
  // Roof Information — customer self-report at intake (see NewCheckForm).
  roofType?: RoofType | null;
  roofMaterial?: RoofMaterial | null;
  roofSlope?: RoofSlope | null;
  roofConstructionYear?: number | null;
  // Electrical Information + Electricity Consumption — customer
  // self-report at intake. The vendor's own in-person electrical
  // inspection lives on VendorJob.electricalAssessment instead.
  electricityBoard?: string | null;
  consumerNumber?: string | null;
  connectionType?: ConnectionType | null;
  sanctionedLoadKw?: number | null;
  contractDemandKva?: number | null;
  connectedLoadKw?: number | null;
  monthlyConsumptionKwh: MonthlyConsumptionEntry[];
  // Battery Requirement — customer's own interest/need, self-reported
  // at intake. The vendor's own physical assessment lives on
  // VendorJob.batteryAssessment instead.
  batteryRequired?: boolean | null;
  backupRequired?: boolean | null;
  requiredBackupHours?: number | null;
  criticalLoads?: string | null;
  /** repositories/vendors.py::get_latest_job_for_site() — the survey
   *  job's own lifecycle status ("queued"|"accepted"|"in_progress"|
   *  "submitted"|"sla_at_risk"|"overdue"), never a vendor's name/
   *  contact details. null when no survey has ever been queued. */
  surveyJobStatus?: string | null;
  /** StartCheckWizard's map-selection metadata (lat/lng/zoom/mapTypeId of
   *  the confirmed satellite view) — null for any check not created
   *  through the map wizard. */
  mapViewMetadata?: {
    zoom: number;
    mapTypeId: string;
    clickedLat: number;
    clickedLng: number;
    selectionMethod?: "crop" | "freehand";
  } | null;
  /** routers/app_sites.py::ElectricalReadinessOut — a customer-safe
   *  subset of the vendor's real, submitted ElectricalAssessment
   *  (see that model's docstring for the exact field-by-field
   *  derivation). null until a vendor has actually submitted an
   *  electrical assessment for this site's survey job — never a
   *  guessed/default checklist. */
  electricalReadiness?: ElectricalReadiness | null;
}

export interface ElectricalReadiness {
  meterAvailable?: boolean | null;
  panelChecked?: boolean | null;
  earthingAvailable?: boolean | null;
  inverterLocationAvailable?: boolean | null;
  cableRouteAvailable?: boolean | null;
}

export interface CompositeSite {
  id: string;
  name: string;
  feederOrDt: string;
  memberSiteIds: string[];
  aggregateCapacityKwp: number;
  createdAt: string;
}

export type ImportJobStatus = "queued" | "running" | "partial" | "complete" | "failed";

export interface ImportRowResult {
  row: number;
  identifier: string;
  status: "success" | "error" | "warning";
  message?: string;
}

export interface ImportJob {
  id: string;
  fileName: string;
  status: ImportJobStatus;
  totalRows: number;
  processedRows: number;
  errorRows: number;
  createdAt: string;
  createdBy: string;
  rows: ImportRowResult[];
}

export interface HistoryEvent {
  id: string;
  siteId: string;
  actor: string;
  timestamp: string;
  kind: "assessment" | "boundary_edit" | "usn_capture" | "note" | "field_survey" | "created";
  summary: string;
  supersededFields?: { field: string; oldValue: string; newValue: string }[];
}

export interface CalibrationProposal {
  id: string;
  jurisdiction: string;
  metric: string;
  remoteValue: number;
  measuredValue: number;
  variancePct: number;
  sampleSize: number;
  proposedAdjustment: string;
  status: "pending_approval" | "approved" | "rejected";
  proposedAt: string;
  proposedBy: string;
}

export interface ModelVersionProposal {
  id: string;
  modelName: string;
  version: string;
  status: "proposed" | "approved" | "rejected" | "active";
  metrics: { label: string; value: string }[];
  proposedAt: string;
  proposedBy: string;
  changelog: string;
}

export interface JurisdictionConstraintPack {
  id: string;
  jurisdiction: string;
  state: string;
  version: string;
  updatedAt: string;
  rules: { name: string; kind: ConstraintKind; description: string }[];
}

// -----------------------------------------------------------------------------
// Vendor portal types
// -----------------------------------------------------------------------------

export type VendorJobStatus =
  | "queued"
  | "accepted"
  | "in_progress"
  | "submitted"
  | "sla_at_risk"
  | "overdue"
  // A vendor turning down an offered job — preserved (not deleted) so
  // an admin can still see and reassign it.
  | "declined";

// In-person survey data (spec sections 3 "Roof Layout/Obstacles" and 7
// "Structural Assessment") — vendor-captured, on-site, during the job.
export type ObstacleType =
  | "WATER_TANK"
  | "OVERHEAD_TANK"
  | "STAIRCASE_ROOM"
  | "LIFT_ROOM"
  | "SOLAR_WATER_HEATER"
  | "EXISTING_SOLAR_PANEL"
  | "AC_OUTDOOR_UNIT"
  | "PIPE"
  | "VENTILATION"
  | "ELECTRICAL_EQUIPMENT"
  | "ANTENNA"
  | "SATELLITE_DISH"
  | "CHIMNEY"
  | "TREE"
  | "ADJACENT_BUILDING"
  | "PARAPET_WALL"
  | "OTHER";

export interface ObstacleSurveyItem {
  id: string;
  type: ObstacleType;
  location?: string | null;
  lengthM?: number | null;
  widthM?: number | null;
  heightM?: number | null;
  distanceFromEdgeM?: number | null;
  lat?: number | null;
  lng?: number | null;
  photoDataUrl?: string | null;
  notes?: string | null;
}

export type StructuralCondition = "NEW" | "GOOD" | "AVERAGE" | "POOR" | "DAMAGED" | "UNDER_CONSTRUCTION";
export type StructuralAssessmentStatus = "pending" | "complete" | "needs_engineer";

export interface StructuralAssessment {
  roofStructuralType?: string | null;
  rccSlabThicknessMm?: number | null;
  structuralCondition?: StructuralCondition | null;
  hasCracks?: boolean | null;
  hasWaterLeakage?: boolean | null;
  hasCorrosion?: boolean | null;
  hasStructuralDamage?: boolean | null;
  existingLoadKgM2?: number | null;
  additionalLoadCapacityKgM2?: number | null;
  recommendedMountingStructure?: string | null;
  inspectionRequired?: boolean | null;
  engineerApprovalRequired?: boolean | null;
  structuralCertificateAvailable?: boolean | null;
  structuralCertificateDataUrl?: string | null;
  assessmentStatus: StructuralAssessmentStatus;
  estimatedPanelWeightKg?: number | null;
  mountingStructureWeightKg?: number | null;
  totalAdditionalLoadKg?: number | null;
  loadPerSqmKg?: number | null;
  roofLoadCapacityKgM2?: number | null;
  safetyMarginPct?: number | null;
  notes?: string | null;
}

export interface ElectricalAssessment {
  meterType?: string | null;
  smartMeter?: boolean | null;
  netMeter?: boolean | null;
  existingSolarMeter?: boolean | null;
  meterLocation?: string | null;
  meterPhotoDataUrl?: string | null;
  mainDbLocation?: string | null;
  mainDbPhotoDataUrl?: string | null;
  dbCondition?: string | null;
  availableSpace?: string | null;
  cableCondition?: string | null;
  earthingAvailable?: boolean | null;
  earthingCondition?: string | null;
  lightningProtectionAvailable?: boolean | null;
  notes?: string | null;
}

export interface InstallationConstraints {
  roofAccessAvailable?: boolean | null;
  staircaseAvailable?: boolean | null;
  liftAvailable?: boolean | null;
  materialTransportationPossible?: boolean | null;
  craneRequired?: boolean | null;
  ladderAccess?: boolean | null;
  installationPathway?: string | null;
  roofEntryPermission?: boolean | null;
  workingSpaceAvailable?: boolean | null;
  panelCleaningAccess?: boolean | null;
  maintenanceAccess?: boolean | null;
  fireAccess?: boolean | null;
  emergencyAccess?: boolean | null;
  notes?: string | null;
}

export type FireRisk = "low" | "medium" | "high";

export interface SafetyAssessment {
  properEarthing?: boolean | null;
  lightningProtection?: boolean | null;
  surgeProtection?: boolean | null;
  dcIsolator?: boolean | null;
  acIsolator?: boolean | null;
  properCableRouting?: boolean | null;
  cableProtection?: boolean | null;
  electricalPanelCondition?: string | null;
  parapetWall?: boolean | null;
  fallProtection?: boolean | null;
  safeRoofAccess?: boolean | null;
  walkwayAvailable?: boolean | null;
  panelMaintenanceClearance?: boolean | null;
  structuralStability?: boolean | null;
  fireRisk?: FireRisk | null;
  fireEquipmentAvailable?: boolean | null;
  emergencyAccess?: boolean | null;
  inverterLocation?: string | null;
  batteryLocation?: string | null;
  notes?: string | null;
}

export type BatteryTechnology = "LITHIUM_ION" | "LEAD_ACID" | "OTHER";

export interface BatteryAssessment {
  batteryRoomAvailable?: boolean | null;
  batteryLocation?: string | null;
  ventilationAvailable?: boolean | null;
  fireSafetyMeasures?: string | null;
  recommendedBatteryCapacityKwh?: number | null;
  recommendedBatteryTechnology?: BatteryTechnology | null;
  notes?: string | null;
}

export interface VendorJob {
  id: string;
  siteId: string;
  siteName: string;
  siteType: SiteType;
  district: string;
  state: string;
  deadline: string;
  payoutInr: number;
  status: VendorJobStatus;
  assignedAt: string;
  requirements: string[];
  distanceKm: number | null;
  submittedAt?: string;
  estimatedCapacityKwp?: number;
  measuredCapacityKwp?: number;
  reconciledPayoutInr?: number;
  variancePct?: number;
  disputeStatus?: "none" | "open" | "resolved";
  disputeReason?: string;
  panoramaPhotoDataUrl?: string;
  shadingNotes?: string;
  obstacleSurvey: ObstacleSurveyItem[];
  structuralAssessment: StructuralAssessment | null;
  electricalAssessment: ElectricalAssessment | null;
  installationConstraints: InstallationConstraints | null;
  safetyAssessment: SafetyAssessment | null;
  batteryAssessment: BatteryAssessment | null;
}

export interface VendorServiceArea {
  region: string;
  districts: string[];
}

export interface VendorPayoutMethod {
  type: "UPI" | "Bank transfer";
  maskedAccount: string;
}

export interface VendorProfile {
  vendorId: string;
  name: string;
  verificationStatus: "verified" | "pending" | "rejected";
  serviceArea: VendorServiceArea;
  availability: boolean;
  accuracyScore: number;
  payoutMethod: VendorPayoutMethod;
  documents: string[];
  joinedAt: string;
  legalName: string | null;
  contactPhone: string | null;
  contactEmail: string | null;
}

export interface VendorNotificationPreferences {
  newJobAssignment: boolean;
  jobDeadlineReminders: boolean;
  jobReassignment: boolean;
  submissionAndPayoutUpdates: boolean;
  disputeUpdates: boolean;
  installationUpdates: boolean;
}

export type PayoutEntryStatus = "pending" | "paid" | "disputed";

export interface PayoutEntry {
  id: string;
  jobId: string;
  amount: number;
  status: PayoutEntryStatus;
  date: string;
  method: "UPI" | "Bank transfer";
}

// -----------------------------------------------------------------------------
// Super admin portal types
// -----------------------------------------------------------------------------

export type VendorVerificationStatus = "verified" | "pending" | "rejected" | "suspended";

export interface AdminVendorSummary {
  id: string;
  name: string;
  verificationStatus: VendorVerificationStatus;
  accuracyScore: number;
  slaCompliancePct: number;
  activeJobs: number;
  totalJobsCompleted: number;
  averageRating?: number | null;
  reviewCount?: number;
  serviceArea: string;
  joinedAt: string;
  payoutMethod: "UPI" | "Bank transfer";
  legalName?: string | null;
  gstNumber?: string | null;
  panNumber?: string | null;
  contactName?: string | null;
  contactPhone?: string | null;
  contactEmail?: string | null;
  addressLine1?: string | null;
  addressLine2?: string | null;
  city?: string | null;
  state?: string | null;
  pincode?: string | null;
  certifications?: string[];
}

export interface FeatureFlag {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
}

export interface ServiceApiKey {
  service: string;
  maskedValue: string;
  lastRotatedAt: string | null;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  timestamp: string;
  details: string;
  // Structured fields backing the Super Admin activity screen's filters
  // and before/after diff view — all optional since an older row (or an
  // action with no customer/vendor to reference) may not carry every one.
  actorId?: string | null;
  actorType?: string | null;
  actorRole?: string | null;
  entityType?: string | null;
  entityId?: string | null;
  projectId?: string | null;
  surveyId?: string | null;
  customerId?: string | null;
  vendorId?: string | null;
  previousValue?: Record<string, unknown> | null;
  newValue?: Record<string, unknown> | null;
  reason?: string | null;
  ipAddress?: string | null;
  userAgent?: string | null;
}

export interface ApiQuota {
  service: string;
  used: number;
  limit: number;
  unit: string;
}

export interface PlatformHealthMetric {
  uptimePct: number;
  incidentsThisMonth: number;
  quotas: ApiQuota[];
}

// -----------------------------------------------------------------------------
// Installation projects — everything AFTER the customer accepts their
// quotation. Backed by repositories/installations.py's four tables and
// the three routers over them (app_checks.py's customer endpoints,
// app_vendor_installations.py, app_admin_installations.py).
// -----------------------------------------------------------------------------

/** The ordered install pipeline. Mirrors
 *  repositories/installations.py::INSTALLATION_STAGES exactly — but the
 *  backend also SENDS the list on every project (`stages`), so prefer the
 *  server's copy for rendering and keep this only for typing a single
 *  stage value. */
export type InstallationStage =
  | "created"
  | "material_procurement"
  | "material_delivered"
  | "installation_started"
  | "mounting_installed"
  | "panels_installed"
  | "inverter_installed"
  | "dc_wiring"
  | "ac_wiring"
  | "earthing"
  | "lightning_protection"
  | "electrical_testing"
  | "inspection"
  | "net_metering"
  | "commissioning"
  | "completed";

export const INSTALLATION_STAGES: InstallationStage[] = [
  "created",
  "material_procurement",
  "material_delivered",
  "installation_started",
  "mounting_installed",
  "panels_installed",
  "inverter_installed",
  "dc_wiring",
  "ac_wiring",
  "earthing",
  "lightning_protection",
  "electrical_testing",
  "inspection",
  "net_metering",
  "commissioning",
  "completed",
];

/** Human-facing copy for each stage. The backend deliberately emits only
 *  the symbolic keys (same contract as ASSESSMENT_STAGES on the
 *  processing screen) — every label lives here, on the frontend. */
export const INSTALLATION_STAGE_LABEL: Record<string, string> = {
  created: "Project opened",
  material_procurement: "Material procurement",
  material_delivered: "Material delivered",
  installation_started: "Installation started",
  mounting_installed: "Mounting structure installed",
  panels_installed: "Panels installed",
  inverter_installed: "Inverter installed",
  dc_wiring: "DC wiring",
  ac_wiring: "AC wiring",
  earthing: "Earthing",
  lightning_protection: "Lightning protection",
  electrical_testing: "Electrical testing",
  inspection: "Inspection",
  net_metering: "Net metering",
  commissioning: "Commissioning",
  completed: "Completed",
};

export interface InstallationProject {
  id: string;
  siteId: string;
  /** Provenance — the survey job that led here. Null when the assessment
   *  was approved without a surviving vendor_jobs row. */
  vendorJobId?: string | null;
  assignedVendorId?: string | null;
  /** A free-form string on the backend by design (VendorJobRow.status's
   *  convention — no state machine); in practice always an
   *  InstallationStage. Typed loosely so an unrecognised value renders
   *  rather than breaking the union. */
  status: string;
  approvedCapacityKwp: number;
  panelModel?: string | null;
  inverterModel?: string | null;
  createdAt: string;
  updatedAt: string;
  /** Position of `status` within `stages`, or -1 if `status` isn't a
   *  known stage — derived server-side, never stored. */
  stageIndex: number;
  /** The full ordered stage list, sent by the backend so a progress
   *  strip never hardcodes the pipeline. */
  stages: string[];
}

/** The ~20 QC items, keyed by repositories/installations.py::
 *  QC_CHECKLIST_ITEMS. Each value is nullable on purpose: null means
 *  "not yet inspected", which is a genuinely different state from false
 *  ("inspected and failed"). */
export type InstallationQcItems = Record<string, boolean | null>;

export const QC_CHECKLIST_ITEMS: string[] = [
  "panel_alignment",
  "panel_spacing",
  "mounting_structure",
  "roof_anchoring",
  "waterproofing",
  "dc_cable_routing",
  "ac_cable_routing",
  "cable_protection",
  "mc4_connections",
  "dc_isolator",
  "ac_isolator",
  "inverter_installation",
  "earthing",
  "lightning_protection",
  "safety_labels",
  "warning_signs",
  "electrical_connections",
  "roof_damage_check",
  "water_leakage_check",
  "final_system_testing",
];

export const QC_CHECKLIST_LABEL: Record<string, string> = {
  panel_alignment: "Panel alignment",
  panel_spacing: "Panel spacing",
  mounting_structure: "Mounting structure",
  roof_anchoring: "Roof anchoring",
  waterproofing: "Waterproofing",
  dc_cable_routing: "DC cable routing",
  ac_cable_routing: "AC cable routing",
  cable_protection: "Cable protection",
  mc4_connections: "MC4 connections",
  dc_isolator: "DC isolator",
  ac_isolator: "AC isolator",
  inverter_installation: "Inverter installation",
  earthing: "Earthing",
  lightning_protection: "Lightning protection",
  safety_labels: "Safety labels",
  warning_signs: "Warning signs",
  electrical_connections: "Electrical connections",
  roof_damage_check: "Roof damage check",
  water_leakage_check: "Water leakage check",
  final_system_testing: "Final system testing",
};

export interface InstallationQcChecklist {
  projectId: string;
  checklist: InstallationQcItems;
  notes?: string | null;
  /** Stamped when the vendor declares the checklist done — the
   *  precondition for the admin's approval gate. */
  submittedAt?: string | null;
  approvedAt?: string | null;
  approvedBy?: string | null;
}

/** A geotagged progress photo. `dataUrl` is an inline base64 data URL:
 *  there is no file-storage service in this project, same convention as
 *  ObstacleSurveyItem.photoDataUrl. */
export interface InstallationPhoto {
  id: string;
  projectId: string;
  stage: string;
  lat?: number | null;
  lng?: number | null;
  dataUrl: string;
  capturedAt: string;
  surveyor?: string | null;
}

export interface CommissioningRecord {
  projectId: string;
  installedCapacityKwp?: number | null;
  installedPanelCount?: number | null;
  panelSerialNumbers: string[];
  inverterSerialNumber?: string | null;
  meterNumber?: string | null;
  voltageReading?: number | null;
  currentReading?: number | null;
  earthingTestPassed?: boolean | null;
  insulationTestPassed?: boolean | null;
  commissioningDate?: string | null;
  /** The three-way sign-off. Each flag is written only by its own
   *  endpoint — the vendor's submission, the customer's acceptance and
   *  the admin's approval never overwrite one another. */
  customerAccepted: boolean;
  vendorConfirmed: boolean;
  adminApproved: boolean;
  finalPhotoDataUrls: string[];
}

/** The customer-safe projection of an installation project — no vendor
 *  contact details and no reviewer identity, the same discipline the
 *  assessment's own reviewStatus subset applies. */
export interface CustomerInstallation {
  id: string;
  siteId: string;
  status: string;
  stageIndex: number;
  stages: string[];
  approvedCapacityKwp: number;
  panelModel?: string | null;
  inverterModel?: string | null;
  createdAt: string;
  updatedAt: string;
  qcApproved: boolean;
  commissioningSubmitted: boolean;
  customerAccepted: boolean;
  adminApproved: boolean;
  reviewed: boolean;
}
