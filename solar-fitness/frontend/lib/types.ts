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

export interface CeilingLedgerEntry {
  label: string;
  kwp: number;
  kind: ConstraintKind;
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
}

export interface Assessment {
  id: string;
  siteId: string;
  verdict: Verdict;
  capacityKwp: number;
  confidence: ConfidenceTier;
  bindingConstraint: BindingConstraint | null;
  reasons: string[];
  ceilingLedger: CeilingLedgerEntry[];
  visionRefinement?: {
    applied: boolean;
    deltaKwp: number;
    note: string;
  };
  panoramaUrl?: string | null;
  mlSuitabilityScore?: number | null;
  generation?: GenerationEstimate;
  cache: CacheProvenance;
  assessedAt: string;
  modelVersion: string;
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
  | "overdue";

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

export interface VendorAccuracyPoint {
  label: string;
  score: number;
}

export interface VendorProfile {
  vendorId: string;
  name: string;
  verificationStatus: "verified" | "pending" | "rejected";
  serviceArea: VendorServiceArea;
  availability: boolean;
  accuracyScore: number;
  accuracyTrend: VendorAccuracyPoint[];
  payoutMethod: VendorPayoutMethod;
  documents: string[];
  joinedAt: string;
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
