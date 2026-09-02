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

export interface GenerationEstimate {
  p50AnnualKwh: number;
  p90AnnualKwh: number;
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
  distanceKm: number;
  submittedAt?: string;
  estimatedCapacityKwp?: number;
  measuredCapacityKwp?: number;
  reconciledPayoutInr?: number;
  variancePct?: number;
  disputeStatus?: "none" | "open" | "resolved";
  disputeReason?: string;
  panoramaPhotoDataUrl?: string;
  shadingNotes?: string;
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
