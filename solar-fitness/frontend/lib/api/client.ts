// -----------------------------------------------------------------------------
// Real API client — every function below calls the FastAPI backend via
// lib/api/fetchClient.ts's apiFetch()/apiUpload(). Function signatures
// (names, params, return types) are unchanged from the mock client this
// replaced, so lib/query/hooks.ts and every component built against it
// needed no changes beyond the handful of real contract differences noted
// inline (USN capture's multi-step flow, admin assessments' lack of
// server-side search/site-name, calibration/model-version approve/reject
// returning an action receipt rather than the full updated row).
// -----------------------------------------------------------------------------

import { apiFetch, apiUpload, ApiError } from "@/lib/api/fetchClient";
import type { CustomerProfile } from "@/lib/fixtures/customer";
import type {
  AdminVendorSummary,
  Assessment,
  AuditLogEntry,
  BindingConstraint,
  CalibrationProposal,
  CommissioningRecord,
  CompositeSite,
  ConfidenceTier,
  CustomerInstallation,
  BatteryAssessment,
  ConnectionType,
  ConstraintKind,
  ElectricalAssessment,
  FinancialProjection,
  GenerationEstimate,
  InstallationConstraints,
  InstallationPhoto,
  InstallationProject,
  InstallationQcChecklist,
  InstallationQcItems,
  MonthlyConsumptionEntry,
  ObstacleSurveyItem,
  RoofMaterial,
  RoofSlope,
  RoofType,
  SafetyAssessment,
  StructuralAssessment,
  FeatureFlag,
  HistoryEvent,
  ImportJob,
  JurisdictionConstraintPack,
  ModelVersionProposal,
  PayoutEntry,
  PlatformHealthMetric,
  ServiceApiKey,
  Site,
  SiteType,
  Verdict,
  VendorJob,
  VendorNotificationPreferences,
  VendorProfile,
} from "@/lib/types";

export { ApiError } from "@/lib/api/fetchClient";

// -----------------------------------------------------------------------------
// Site / portfolio
// -----------------------------------------------------------------------------

export interface SiteListParams {
  q?: string;
  siteType?: string;
  verdict?: string;
  state?: string;
  page?: number;
  pageSize?: number;
}

export async function listSites(params: SiteListParams = {}): Promise<{ items: Site[]; total: number }> {
  return apiFetch("/app/sites", { query: { ...params } });
}

export async function getSite(siteId: string): Promise<Site> {
  return apiFetch(`/app/sites/${siteId}`);
}

export async function getSiteHistory(siteId: string): Promise<HistoryEvent[]> {
  return apiFetch(`/app/sites/${siteId}/history`);
}

export async function listImportJobs(): Promise<ImportJob[]> {
  return apiFetch("/app/imports");
}

export async function getImportJob(jobId: string): Promise<ImportJob> {
  return apiFetch(`/app/imports/${jobId}`);
}

export async function listComposites(): Promise<CompositeSite[]> {
  return apiFetch("/app/composites");
}

export async function listCalibrationProposals(): Promise<CalibrationProposal[]> {
  return apiFetch("/app/admin/calibration-proposals");
}

// The approve/reject endpoints return a small action receipt, not the full
// updated proposal — re-fetch the list and return this item's fresh copy so
// callers (useCalibrationDecision in lib/query/hooks.ts) keep getting a full
// CalibrationProposal back, same as the mock always did.
export async function approveCalibrationProposal(id: string): Promise<CalibrationProposal> {
  await apiFetch(`/app/admin/calibration-proposals/${id}/approve`, { method: "POST" });
  return getCalibrationProposalOrThrow(id);
}

export async function rejectCalibrationProposal(id: string): Promise<CalibrationProposal> {
  await apiFetch(`/app/admin/calibration-proposals/${id}/reject`, { method: "POST" });
  return getCalibrationProposalOrThrow(id);
}

async function getCalibrationProposalOrThrow(id: string): Promise<CalibrationProposal> {
  const items = await listCalibrationProposals();
  const item = items.find((c) => c.id === id);
  if (!item) throw new ApiError("Calibration proposal not found", 404);
  return item;
}

export async function listModelVersions(): Promise<ModelVersionProposal[]> {
  return apiFetch("/app/admin/model-versions");
}

export async function approveModelVersion(id: string): Promise<ModelVersionProposal> {
  await apiFetch(`/app/admin/model-versions/${id}/approve`, { method: "POST" });
  return getModelVersionOrThrow(id);
}

export async function rejectModelVersion(id: string): Promise<ModelVersionProposal> {
  await apiFetch(`/app/admin/model-versions/${id}/reject`, { method: "POST" });
  return getModelVersionOrThrow(id);
}

async function getModelVersionOrThrow(id: string): Promise<ModelVersionProposal> {
  const items = await listModelVersions();
  const item = items.find((m) => m.id === id);
  if (!item) throw new ApiError("Model version not found", 404);
  return item;
}

export async function listJurisdictions(): Promise<JurisdictionConstraintPack[]> {
  return apiFetch("/app/jurisdictions");
}

export async function publishJurisdiction(pack: string): Promise<JurisdictionConstraintPack> {
  return apiFetch(`/app/admin/jurisdictions/${pack}/publish`, { method: "POST" });
}

// -----------------------------------------------------------------------------
// USN capture — the backend splits this into 4 endpoints (manual entry;
// bill-OCR preview; payment-proof-OCR preview; confirm), where OCR is a
// two-step "extract a preview, then confirm/correct it" flow rather than
// the mock's single submitUsn() call. See components/sites/UsnCaptureFlow.tsx.
// -----------------------------------------------------------------------------

export interface UsnCaptureResult {
  usn: string | null;
  usnSource: string | null;
}

export async function captureManualUsn(siteId: string, usn: string): Promise<UsnCaptureResult> {
  return apiFetch(`/app/sites/${siteId}/usn/manual`, { method: "POST", body: { usn } });
}

export interface UsnExtractionPreview {
  uploadId: string;
  usn: string | null;
  usnSource: string;
  extractionStatus: "extracted" | "not_found" | "failed";
}

export async function extractUsnFromBill(siteId: string, file: File): Promise<UsnExtractionPreview> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload(`/app/sites/${siteId}/usn/bill`, formData);
}

export async function extractUsnFromPaymentProof(siteId: string, file: File): Promise<UsnExtractionPreview> {
  const formData = new FormData();
  formData.append("file", file);
  return apiUpload(`/app/sites/${siteId}/usn/payment-proof`, formData);
}

export async function confirmUsn(siteId: string, uploadId: string, confirmedUsn: string): Promise<UsnCaptureResult> {
  return apiFetch(`/app/sites/${siteId}/usn/confirm`, {
    method: "POST",
    body: { uploadId, confirmedUsn },
  });
}

export async function saveBoundary(siteId: string, points: { lat: number; lng: number }[]): Promise<Site> {
  return apiFetch(`/app/sites/${siteId}/boundary`, { method: "PUT", body: { points } });
}

/**
 * GEO-02 — a customer's own traced roof outline.
 *
 * Check-scoped rather than reusing saveBoundary() above: /app/sites/*
 * authorises through the user's owner_org, which an individual signup
 * does not have, so that route 404s for exactly the people this screen
 * is for. Same validation, versioning and provenance behind it.
 */
export async function saveCheckBoundary(
  checkId: string,
  points: { lat: number; lng: number }[]
): Promise<Site> {
  return apiFetch(`/app/checks/${checkId}/boundary`, { method: "PUT", body: { points } });
}

export async function createSite(input: {
  name: string;
  siteType: Site["siteType"];
  address: string;
  district: string;
  state: string;
  lat: number;
  lng: number;
}): Promise<Site> {
  return apiFetch("/app/sites", { method: "POST", body: input });
}

export interface PortfolioSummary {
  totalSites: number;
  totalCapacityKwp: number;
  verdictBreakdown: Record<string, number>;
  activeJobs: number;
  siteTypeBreakdown: Record<string, number>;
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  return apiFetch("/app/sites/portfolio-summary");
}

// -----------------------------------------------------------------------------
// Vendor portal
// -----------------------------------------------------------------------------

export interface VendorJobListParams {
  status?: string;
  sort?: "deadline" | "distance" | "payout";
}

export async function listVendorJobs(params: VendorJobListParams = {}): Promise<VendorJob[]> {
  return apiFetch("/app/vendor/jobs", { query: { ...params } });
}

export async function getVendorJob(jobId: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}`);
}

export async function acceptVendorJob(jobId: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/accept`, { method: "POST" });
}

export async function declineVendorJob(jobId: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/decline`, { method: "POST" });
}

export async function startVendorJob(jobId: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/start`, { method: "POST" });
}

export async function submitVendorJob(jobId: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/submit`, { method: "POST" });
}

export async function uploadPanoramaPhoto(jobId: string, dataUrl: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/panorama`, { method: "PATCH", body: { dataUrl } });
}

export async function saveShadingNotes(jobId: string, notes: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/shading-notes`, { method: "PATCH", body: { notes } });
}

export async function submitFieldBoundary(
  jobId: string,
  points: { lat: number; lng: number }[]
): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/boundary`, { method: "PATCH", body: { points } });
}

export async function saveObstacleSurvey(jobId: string, obstacles: ObstacleSurveyItem[]): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/obstacles`, { method: "PATCH", body: { obstacles } });
}

export async function saveStructuralAssessment(
  jobId: string,
  assessment: StructuralAssessment
): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/structural-assessment`, { method: "PATCH", body: assessment });
}

export async function saveElectricalAssessment(
  jobId: string,
  assessment: ElectricalAssessment
): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/electrical-assessment`, { method: "PATCH", body: assessment });
}

export async function saveInstallationConstraints(
  jobId: string,
  constraints: InstallationConstraints
): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/installation-constraints`, { method: "PATCH", body: constraints });
}

export async function saveSafetyAssessment(jobId: string, assessment: SafetyAssessment): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/safety-assessment`, { method: "PATCH", body: assessment });
}

export async function saveBatteryAssessment(jobId: string, assessment: BatteryAssessment): Promise<VendorJob> {
  return apiFetch(`/app/vendor/jobs/${jobId}/battery-assessment`, { method: "PATCH", body: assessment });
}

export async function getVendorProfile(): Promise<VendorProfile> {
  return apiFetch("/app/vendor/profile");
}

export async function updateVendorAvailability(available: boolean): Promise<VendorProfile> {
  return apiFetch("/app/vendor/profile/availability", { method: "PATCH", body: { available } });
}

export async function getVendorNotificationPreferences(): Promise<VendorNotificationPreferences> {
  return apiFetch("/app/vendor/profile/notification-preferences");
}

export async function updateVendorNotificationPreferences(
  preferences: VendorNotificationPreferences
): Promise<VendorNotificationPreferences> {
  return apiFetch("/app/vendor/profile/notification-preferences", { method: "PATCH", body: preferences });
}

export interface ChangePasswordInput {
  currentPassword: string;
  newPassword: string;
}

export async function changePassword(input: ChangePasswordInput): Promise<void> {
  return apiFetch("/app/auth/change-password", { method: "POST", body: input });
}

export async function listVendorSubmissions(): Promise<VendorJob[]> {
  return apiFetch("/app/vendor/submissions");
}

export async function disputeSubmission(id: string, reason: string): Promise<VendorJob> {
  return apiFetch(`/app/vendor/submissions/${id}/dispute`, { method: "POST", body: { reason } });
}

// -----------------------------------------------------------------------------
// Super admin portal
// -----------------------------------------------------------------------------

export interface AdminVendorListParams {
  q?: string;
  verificationStatus?: string;
  sort?: "accuracy" | "sla";
}

export async function listAdminVendors(params: AdminVendorListParams = {}): Promise<AdminVendorSummary[]> {
  return apiFetch("/app/admin/vendors", { query: { ...params } });
}

export async function getAdminVendor(id: string): Promise<AdminVendorSummary> {
  return apiFetch(`/app/admin/vendors/${id}`);
}

export async function suspendVendor(id: string): Promise<AdminVendorSummary> {
  return apiFetch(`/app/admin/vendors/${id}/suspend`, { method: "POST" });
}

export async function reinstateVendor(id: string): Promise<AdminVendorSummary> {
  return apiFetch(`/app/admin/vendors/${id}/reinstate`, { method: "POST" });
}

export async function listVendorVerificationQueue(): Promise<AdminVendorSummary[]> {
  return apiFetch("/app/admin/vendors/verification-queue");
}

export async function approveVendorVerification(id: string): Promise<AdminVendorSummary> {
  return apiFetch(`/app/admin/vendors/${id}/verification/approve`, { method: "POST" });
}

export async function rejectVendorVerification(id: string): Promise<AdminVendorSummary> {
  return apiFetch(`/app/admin/vendors/${id}/verification/reject`, { method: "POST" });
}

export interface NewVendorInput {
  name: string;
  legalName?: string;
  gstNumber?: string;
  panNumber?: string;
  contactName?: string;
  contactPhone?: string;
  contactEmail: string;
  addressLine1?: string;
  addressLine2?: string;
  city?: string;
  state?: string;
  pincode?: string;
  serviceAreaRegion: string;
  serviceAreaDistricts: string[];
  payoutMethodType: "UPI" | "Bank transfer";
  payoutMaskedAccount: string;
  certifications: string[];
  documents: string[];
}

export interface NewVendorResult {
  vendor: AdminVendorSummary;
  loginEmail: string;
  temporaryPassword: string;
}

export async function createAdminVendor(input: NewVendorInput): Promise<NewVendorResult> {
  return apiFetch("/app/admin/vendors", { method: "POST", body: input });
}

export async function listAdminVendorJobs(vendorId: string): Promise<VendorJob[]> {
  return apiFetch(`/app/admin/vendors/${vendorId}/jobs`);
}

export async function listAdminVendorPayouts(vendorId: string): Promise<PayoutEntry[]> {
  return apiFetch(`/app/admin/vendors/${vendorId}/payouts`);
}

export interface VendorUser {
  id: string;
  email: string;
  name: string;
  status: "active" | "inactive";
  createdAt: string;
  lastLoginAt: string | null;
}

export interface NewVendorUserInput {
  name: string;
  email: string;
}

export interface NewVendorUserResult {
  user: VendorUser;
  loginEmail: string;
  temporaryPassword: string;
}

export async function listVendorUsers(vendorId: string): Promise<VendorUser[]> {
  return apiFetch(`/app/admin/vendors/${vendorId}/users`);
}

export async function createVendorUser(
  vendorId: string,
  input: NewVendorUserInput,
): Promise<NewVendorUserResult> {
  return apiFetch(`/app/admin/vendors/${vendorId}/users`, { method: "POST", body: input });
}

export async function setVendorUserStatus(
  vendorId: string,
  userId: string,
  status: "active" | "inactive",
): Promise<VendorUser> {
  return apiFetch(`/app/admin/vendors/${vendorId}/users/${userId}/status`, {
    method: "PATCH",
    body: { status },
  });
}

// -----------------------------------------------------------------------------
// Notifications
// -----------------------------------------------------------------------------

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  readAt: string | null;
  createdAt: string;
}

export async function listNotifications(): Promise<AppNotification[]> {
  return apiFetch("/app/notifications");
}

export async function markNotificationRead(id: string): Promise<AppNotification> {
  return apiFetch(`/app/notifications/${id}/read`, { method: "POST" });
}

// Customer -> [customer raises an enquiry] -> Admin Review -> Admin
// Approval -> Vendor Access. "not_submitted" = a good verdict the
// customer hasn't turned into an enquiry yet (the check and the enquiry
// are deliberately separate stages); "pending" = the enquiry was raised
// and awaits admin action; "not_applicable" = verdict (CONDITIONAL /
// INSUFFICIENT_DATA / NOT_SUITABLE) never leads to vendor work, so
// there's nothing to raise an enquiry on.
export type ReviewStatus = "not_submitted" | "pending" | "approved" | "rejected" | "not_applicable";

export interface AdminAssessmentRow {
  siteId: string;
  siteName: string;
  address: string | null;
  district: string;
  state: string;
  reviewStatus: ReviewStatus;
  reviewedBy: string | null;
  reviewedAt: string | null;
  rejectionReason: string | null;
  assignedVendorId: string | null;
  vendorJobId: string | null;
  // Enquiry workflow — the customer's own action, distinct from the
  // admin's approve/reject/reassign action above.
  customerSelectedVendorId: string | null;
  enquirySubmittedAt: string | null;
  // A district-matched vendor hint (real matching logic — repositories/
  // vendors.py::best_available_vendor_for_district()), shown only when
  // no customer selection exists. Null when nothing matches.
  suggestedVendorId: string | null;
  assessment: Assessment;
}

export interface AssessmentListParams {
  q?: string;
  verdict?: string;
  reviewStatus?: ReviewStatus;
  page?: number;
  pageSize?: number;
}

// The backend's admin listing has no server-side search/pagination — just
// limit/offset. Fetch a generous page, then filter/paginate client-side the
// same way the mock always did. siteName/address/district/state and the
// review fields are now real (joined from the sites table server-side).
interface RawCapacityResult {
  recommended_kwp: number | null;
}

interface RawAdminAssessment {
  id: string;
  siteId: string;
  siteName: string;
  address: string | null;
  district: string;
  state: string;
  verdict: string;
  confidence: ConfidenceTier;
  bindingConstraint: BindingConstraint;
  reasons: string[];
  capacity: RawCapacityResult;
  panoramaUrl: string | null;
  mlSuitabilityScore: number | null;
  cacheHit: boolean;
  engineVersion: string;
  createdAt: string;
  generation: GenerationEstimate | null;
  reviewStatus: ReviewStatus;
  reviewedBy: string | null;
  reviewedAt: string | null;
  rejectionReason: string | null;
  assignedVendorId: string | null;
  vendorJobId: string | null;
  customerSelectedVendorId: string | null;
  enquirySubmittedAt: string | null;
  suggestedVendorId: string | null;
}

interface RawChecklistItem {
  label: string;
  kwp: number | null;
  kind: ConstraintKind;
  note: string;
  status: "ok" | "estimated" | "insufficient_data" | "not_applicable";
  isBinding: boolean;
}

export type GridConnectionStatus =
  | "not_started"
  | "application_submitted"
  | "under_review"
  | "approved"
  | "connected"
  | "rejected";

export interface GridFeasibility {
  discom?: string | null;
  distributionArea?: string | null;
  netMeteringAvailable?: boolean | null;
  grossMeteringAvailable?: boolean | null;
  applicationRequired?: boolean | null;
  gridApprovalRequired?: boolean | null;
  transformerCapacityKva?: number | null;
  maxPermissibleCapacityKwp?: number | null;
  gridConnectionStatus: GridConnectionStatus;
  applicationReference?: string | null;
  notes?: string | null;
}

export interface FinancialFeasibility {
  panelCostInr?: number | null;
  inverterCostInr?: number | null;
  mountingStructureCostInr?: number | null;
  dcCableCostInr?: number | null;
  acCableCostInr?: number | null;
  protectionEquipmentCostInr?: number | null;
  installationCostInr?: number | null;
  civilWorkCostInr?: number | null;
  transportationCostInr?: number | null;
  otherChargesInr?: number | null;
  totalProjectCostInr?: number | null;
  subsidyApplicable?: boolean | null;
  subsidyCategory?: string | null;
  subsidyAmountInr?: number | null;
  customerContributionInr?: number | null;
  monthlySavingsInr?: number | null;
  annualSavingsInr?: number | null;
  paybackPeriodYears?: number | null;
  tenYearSavingsInr?: number | null;
  twentyYearSavingsInr?: number | null;
  estimatedSystemLifetimeYears?: number | null;
  notes?: string | null;
}

interface RawAdminAssessmentDetail extends RawAdminAssessment {
  checklist: RawChecklistItem[];
  gridFeasibility: GridFeasibility | null;
  financialFeasibility: FinancialFeasibility | null;
}

function toAdminAssessmentRow(raw: RawAdminAssessment): AdminAssessmentRow {
  return {
    siteId: raw.siteId,
    siteName: raw.siteName,
    address: raw.address,
    district: raw.district,
    state: raw.state,
    reviewStatus: raw.reviewStatus,
    reviewedBy: raw.reviewedBy,
    reviewedAt: raw.reviewedAt,
    rejectionReason: raw.rejectionReason,
    assignedVendorId: raw.assignedVendorId,
    vendorJobId: raw.vendorJobId,
    customerSelectedVendorId: raw.customerSelectedVendorId,
    enquirySubmittedAt: raw.enquirySubmittedAt,
    suggestedVendorId: raw.suggestedVendorId,
    assessment: {
      id: raw.id,
      siteId: raw.siteId,
      verdict: raw.verdict as Verdict,
      capacityKwp: raw.capacity.recommended_kwp ?? 0,
      confidence: raw.confidence,
      bindingConstraint: raw.bindingConstraint,
      reasons: raw.reasons,
      ceilingLedger: [],
      panoramaUrl: raw.panoramaUrl,
      mlSuitabilityScore: raw.mlSuitabilityScore,
      generation: raw.generation ?? undefined,
      cache: { cacheHit: raw.cacheHit },
      assessedAt: raw.createdAt,
      modelVersion: raw.engineVersion,
    },
  };
}

export interface AdminAssessmentDetail extends AdminAssessmentRow {
  checklist: RawChecklistItem[];
  gridFeasibility: GridFeasibility | null;
  financialFeasibility: FinancialFeasibility | null;
}

function toAdminAssessmentDetail(raw: RawAdminAssessmentDetail): AdminAssessmentDetail {
  return {
    ...toAdminAssessmentRow(raw),
    checklist: raw.checklist,
    gridFeasibility: raw.gridFeasibility,
    financialFeasibility: raw.financialFeasibility,
  };
}

export async function listAllAssessments(
  params: AssessmentListParams = {}
): Promise<{ items: AdminAssessmentRow[]; total: number }> {
  const raw = await apiFetch<RawAdminAssessment[]>("/app/admin/assessments", { query: { limit: 500, offset: 0 } });
  let items = raw.map(toAdminAssessmentRow);

  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter(
      (row) => row.siteName.toLowerCase().includes(q) || row.siteId.toLowerCase().includes(q) || row.district.toLowerCase().includes(q)
    );
  }
  if (params.verdict) items = items.filter((row) => row.assessment.verdict === params.verdict);
  if (params.reviewStatus) items = items.filter((row) => row.reviewStatus === params.reviewStatus);

  const total = items.length;
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? total;
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), total };
}

export async function getAdminAssessment(id: string): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}`);
  return toAdminAssessmentDetail(raw);
}

export async function approveAssessment(
  id: string,
  input: { vendorId: string; deadlineDays?: number; payoutInr?: number }
): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}/approve`, {
    method: "POST",
    body: { vendorId: input.vendorId, deadlineDays: input.deadlineDays, payoutInr: input.payoutInr },
  });
  return toAdminAssessmentDetail(raw);
}

export async function reassignAssessment(
  id: string,
  input: { vendorId: string; deadlineDays?: number; reason?: string }
): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}/reassign`, {
    method: "POST",
    body: { vendorId: input.vendorId, deadlineDays: input.deadlineDays, reason: input.reason },
  });
  return toAdminAssessmentDetail(raw);
}

export async function rejectAssessment(id: string, reason: string): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}/reject`, {
    method: "POST",
    body: { reason },
  });
  return toAdminAssessmentDetail(raw);
}

export async function saveGridFeasibility(id: string, feasibility: GridFeasibility): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}/grid-feasibility`, {
    method: "PATCH",
    body: feasibility,
  });
  return toAdminAssessmentDetail(raw);
}

export async function saveFinancialFeasibility(
  id: string,
  feasibility: FinancialFeasibility
): Promise<AdminAssessmentDetail> {
  const raw = await apiFetch<RawAdminAssessmentDetail>(`/app/admin/assessments/${id}/financial-feasibility`, {
    method: "PATCH",
    body: feasibility,
  });
  return toAdminAssessmentDetail(raw);
}

export interface AuditLogListParams {
  actor?: string;
  action?: string;
  q?: string;
  // Query key names match the backend's Query(alias=...) exactly — see
  // routers/app_admin_platform.py::list_audit_log — since apiFetch's
  // buildUrl() sends object keys verbatim as query param names.
  actorRole?: string;
  entityType?: string;
  projectId?: string;
  surveyId?: string;
  customerId?: string;
  vendorId?: string;
  since?: string;
  until?: string;
}

export async function listAuditLog(params: AuditLogListParams = {}): Promise<AuditLogEntry[]> {
  return apiFetch("/app/admin/audit-log", { query: { ...params } });
}

export async function getPlatformHealth(): Promise<PlatformHealthMetric> {
  return apiFetch("/app/admin/platform-health");
}

export async function rotateApiKey(service: string): Promise<{ service: string; rotatedAt: string }> {
  return apiFetch("/app/admin/api-keys/rotate", { method: "POST", body: { service } });
}

export async function listServiceApiKeys(): Promise<ServiceApiKey[]> {
  return apiFetch("/app/admin/api-keys");
}

export async function listFeatureFlags(): Promise<FeatureFlag[]> {
  return apiFetch("/app/admin/feature-flags");
}

export async function setFeatureFlag(key: string, enabled: boolean): Promise<FeatureFlag> {
  return apiFetch(`/app/admin/feature-flags/${key}`, { method: "PATCH", body: { enabled } });
}

// -----------------------------------------------------------------------------
// FIN-02 — the versioned, admin-editable financial-projection assumptions.
// Distinct from FinancialEstimate's own config-pack coefficients (those stay
// dev-tunable YAML) — these are the NEW assumptions engine/
// financial_projection.py needs (escalation, export rate, self-consumption
// default, maintenance, financing defaults), live-editable here.
// -----------------------------------------------------------------------------

export interface SeasonCalendarMonths {
  summer: number[];
  rainy: number[];
  winter: number[];
}

export interface FinancialAssumptions {
  version: number;
  tariffEscalationPctPerYear: number;
  exportTariffInrPerKwh: number;
  defaultSelfConsumptionRatio: number;
  annualMaintenanceCostInrPerKwp: number;
  inverterReplacementYear: number | null;
  inverterReplacementCostInrPerKwp: number | null;
  financingDefaultDownPaymentPct: number;
  financingDefaultInterestRatePct: number;
  financingDefaultTenureYears: number;
  // FIN-03 — seasonal consumption/generation model.
  annualConsumptionGrowthPct: number;
  rainySeasonFactorPct: number;
  summerMonths: number;
  rainyMonths: number;
  winterMonths: number;
  summerGenerationShare: number;
  rainyGenerationShare: number;
  winterGenerationShare: number;
  seasonCalendarMonths: SeasonCalendarMonths;
  updatedBy: string | null;
  note: string | null;
  updatedAt: string;
}

export type FinancialAssumptionsInput = Omit<
  FinancialAssumptions,
  "version" | "updatedBy" | "updatedAt"
>;

export async function getFinancialConfig(): Promise<FinancialAssumptions> {
  return apiFetch("/app/admin/financial-config");
}

export async function setFinancialConfig(
  input: FinancialAssumptionsInput
): Promise<FinancialAssumptions> {
  return apiFetch("/app/admin/financial-config", { method: "PATCH", body: input });
}

// -----------------------------------------------------------------------------
// Customer portal (consumer self-service: signup -> point a location -> result)
//
// A "check" is the same shape as a Site with a latestAssessment — this simply
// exposes that model through a simpler, homeowner-facing set of endpoints.
// -----------------------------------------------------------------------------

export async function listChecks(): Promise<Site[]> {
  return apiFetch("/app/checks");
}

export async function getCheck(checkId: string): Promise<Site> {
  return apiFetch(`/app/checks/${checkId}`);
}

// FIN-02 — the year-by-year ROI projection built on top of this check's
// already-persisted FinancialEstimate/generation figures (never
// recomputed). `financing=false` omits the financed-purchase comparison;
// the three override params let the customer explore a different down
// payment/rate/tenure than the admin-configured defaults for this one
// request, without persisting a new assumptions version.
export interface FinancialProjectionParams {
  financing?: boolean;
  downPaymentPct?: number;
  interestRatePct?: number;
  tenureYears?: number;
}

export async function getCheckFinancialProjection(
  checkId: string,
  params: FinancialProjectionParams = {}
): Promise<FinancialProjection> {
  return apiFetch(`/app/checks/${checkId}/financial-projection`, {
    query: {
      financing: params.financing,
      downPaymentPct: params.downPaymentPct,
      interestRatePct: params.interestRatePct,
      tenureYears: params.tenureYears,
    },
  });
}

export interface MapViewMetadata {
  zoom: number;
  mapTypeId: string;
  clickedLat: number;
  clickedLng: number;
  /** StartCheckWizard's Crop vs Freehand building-selection tool. */
  selectionMethod?: "crop" | "freehand";
}

export interface NewCheckInput {
  address: string;
  lat: number;
  lng: number;
  siteType?: SiteType;
  /** CON-05 input. Optional — omitting them sizes the system by roof area
   *  alone, which is what every check did before bills could be captured. */
  monthlyBillLowInr?: number;
  monthlyBillHighInr?: number;
  /** FIN-03 — the PRIMARY consumption figures for seasonal estimation
   *  when the customer knows their units (kWh), not just their bill
   *  amount. Preferred over the ₹ pair above whenever both are given. */
  highestConsumptionKwh?: number;
  lowestConsumptionKwh?: number;
  roofType?: RoofType;
  roofMaterial?: RoofMaterial;
  roofSlope?: RoofSlope;
  roofConstructionYear?: number;
  electricityBoard?: string;
  consumerNumber?: string;
  /** USN-01 — the electricity connection number, captured at intake.
   *  Backend validates against the same 6-20 char format
   *  providers/usn_ocr.py::capture_manual() uses for the post-analysis
   *  manual-entry path on the result page. */
  usn?: string;
  connectionType?: ConnectionType;
  sanctionedLoadKw?: number;
  contractDemandKva?: number;
  connectedLoadKw?: number;
  monthlyConsumptionKwh?: MonthlyConsumptionEntry[];
  batteryRequired?: boolean;
  backupRequired?: boolean;
  requiredBackupHours?: number;
  criticalLoads?: string;
  /** StartCheckWizard: a rooftop polygon the customer already confirmed
   *  on the full-screen map, applied atomically at creation instead of
   *  through a separate saveCheckBoundary() call afterwards. */
  confirmedBoundary?: { lat: number; lng: number }[];
  mapMetadata?: MapViewMetadata;
}

export async function createCheck(input: NewCheckInput): Promise<Site> {
  return apiFetch("/app/checks", { method: "POST", body: input });
}

// -----------------------------------------------------------------------------
// StartCheckWizard's click-to-locate step.
// -----------------------------------------------------------------------------

/** The real, measured plane of whichever roof segment the pin landed on
 *  — routers/app_checks.py::RoofPitchOut, backed by
 *  providers/solar_api.py::roof_pitch_at_point(). Physical roof slope,
 *  never the map camera's own tilt — null whenever no roof segment has
 *  both a pitch and an azimuth to report, rather than a fabricated
 *  value. */
export interface RoofPitchResult {
  segmentIndex: number;
  pitchDeg: number;
  azimuthDeg: number;
  /** 16-point compass label, e.g. "SE". */
  orientation: string;
  planeHeightM: number | null;
  areaM2: number | null;
  groundAreaM2: number | null;
  /** Total roof planes Building Insights reported for this building —
   *  lets the UI say "plane 1 of 3" when the roof isn't a single slope. */
  segmentCount: number;
  matchedBy: "contains" | "tolerated_contains" | "nearest";
  confidence: "high" | "medium" | "low";
}

export interface ResolveBuildingResult {
  status: "ok" | "no_coverage" | "error";
  boundary: { lat: number; lng: number }[] | null;
  centroid: { lat: number; lng: number } | null;
  areaM2: number | null;
  /** "solar_api_mask" is a real traced outline; "solar_api" is Google's
   *  bounding-box rectangle — the same distinction SiteOut.geometrySource
   *  already carries for a created check's boundary. */
  source: "solar_api_mask" | "solar_api" | null;
  imageryQuality: string | null;
  /** ISO date string — when the imagery this detection ran on was
   *  captured. Null when Google didn't report one. */
  imageryDate: string | null;
  competingBuildingsNearby: number | null;
  detail: string | null;
  roofPitch: RoofPitchResult | null;
}

export async function resolveBuildingAt(lat: number, lng: number): Promise<ResolveBuildingResult> {
  return apiFetch("/app/checks/resolve-building", { query: { lat, lng } });
}

// -----------------------------------------------------------------------------
// Real backend-driven progress for the processing screen
// (routers/assessments.py::ASSESSMENT_STAGES). Previously completeCheck
// blocked on one request until the whole pipeline finished, with the
// wait masked behind a fixed ~3s client-side animation regardless of how
// long the real work actually took. Now it only starts a background job
// and returns a job id; getCheckAssessmentStatus is polled to find out
// when — and at what stage — it actually is.
// -----------------------------------------------------------------------------

export interface StartAssessmentJob {
  jobId: string;
}

/** One of routers/assessments.py::ASSESSMENT_STAGES's keys. This app owns
 *  the human-facing copy for each — see ProcessingClient.tsx's STAGE_COPY. */
export type AssessmentStage =
  | "resolving_location"
  | "analyzing_roof_imagery"
  | "detecting_obstacles"
  | "computing_usable_area"
  | "sizing_system"
  | "placing_panels"
  | "scoring_feasibility"
  | "finalizing_result";

export type AssessmentJobStatus =
  | "pending"
  | "progress"
  | "ok"
  | "not_found"
  | "geometry_rejected"
  | "error";

export interface AssessmentJobStatusDto {
  jobId: string;
  status: AssessmentJobStatus;
  stage: AssessmentStage | null;
  error: string | null;
}

export async function completeCheck(checkId: string): Promise<StartAssessmentJob> {
  return apiFetch(`/app/checks/${checkId}/complete`, { method: "POST" });
}

export async function getCheckAssessmentStatus(
  checkId: string,
  jobId: string,
): Promise<AssessmentJobStatusDto> {
  return apiFetch(`/app/checks/${checkId}/complete/${jobId}`);
}

export async function getCustomerProfile(): Promise<CustomerProfile> {
  return apiFetch("/app/customer/profile");
}

export async function updateCustomerProfile(input: Partial<CustomerProfile>): Promise<CustomerProfile> {
  return apiFetch("/app/customer/profile", { method: "PATCH", body: input });
}

// -----------------------------------------------------------------------------
// This app's own per-panel solar layout for a check's rooftop
// (engine/panel_packing.py), for drawing over the satellite imagery.
//
// Deliberately its OWN endpoint rather than a field on the check: it is
// presentation-only, and a failure must never take the result page's
// verdict or capacity down with it.
//
// panelCount/totalKwp now describe the SAME system the check's capacityKwp
// names — the layout is packed specifically to reach that figure inside
// the resolved usable polygon, obstacle- and setback-aware. They can
// differ by up to one panel's worth (a packed layout can't hit an
// arbitrary kWp exactly), but should never disagree by more than that.
// -----------------------------------------------------------------------------

export interface SolarPanelPolygonDto {
  corners: { lat: number; lng: number }[];
  capacityWatts: number | null;
  orientation: string;
  segmentIndex: number | null;
  azimuthDegrees: number | null;
  pitchDegrees: number | null;
}

// engine/panel_validation.py::validate_layout()'s independent re-check —
// panelsOutsideRoof/panelsIntersectingObstacles should always be 0; this
// makes that a checked, reported number rather than an assumption.
// Absent on assessments computed before this field existed.
export interface SolarLayoutValidation {
  panelCount: number;
  rejectedCount: number;
  panelsOutsideRoof: number;
  panelsIntersectingObstacles: number;
}

export interface SolarLayout {
  status: "ok" | "no_layout" | "no_data";
  reason: string | null;
  source: string;
  panelCount: number;
  totalKwp: number;
  panels: SolarPanelPolygonDto[];
  validation?: SolarLayoutValidation | null;
}

export async function getCheckSolarLayout(checkId: string): Promise<SolarLayout> {
  return apiFetch(`/app/checks/${checkId}/solar-layout`);
}

// -----------------------------------------------------------------------------
// The 3D rooftop viewer's data source — engine/panorama.py::
// build_scene_geometry()'s roof + walls + this app's own packed panel array +
// mounting-rack visuals + OBS-04's applied obstacles (real DSM/segment-plane/
// panel-layout geometry, the same source of truth the .glb pipeline above
// uses) as plain JSON for the client-side Three.js scene on the result page
// (components/panorama/Scene3DViewer.tsx).
// -----------------------------------------------------------------------------

export interface SceneMeshDto {
  /** [x, y, z] metres — x east, y north, z up, ground at z = 0. */
  vertices: number[][];
  /** [i, j, k] indices into `vertices`. */
  faces: number[][];
  /** Per-vertex RGB, 0..1, same order as `vertices` — the roof's
   *  sunshine-tint heatmap, or the panel array's frame/glass colouring.
   *  null for a mesh that was never vertex-coloured (walls, an
   *  obstacle box, or a roof/panel array with no shading data to tint
   *  from). */
  colors: number[][] | null;
}

export interface SceneObstacleDto {
  id: string;
  /** domain/assessment.py::ObstacleType — water_tank/hvac_unit/chimney/
   *  existing_solar_panel/vent/antenna/other. null for an obstacle
   *  applied before this field existed. */
  type: string | null;
  mesh: SceneMeshDto;
}

export interface SceneGeometry {
  status: "ok" | "not_generated" | "no_data";
  reason: string | null;
  originLat: number | null;
  originLng: number | null;
  heightM: number | null;
  groundSource: "measured" | "fallback" | null;
  roof: SceneMeshDto | null;
  walls: SceneMeshDto | null;
  /** This app's OWN packed panel array (Assessment.panel_layout) placed
   *  in 3D — NOT Google's solarPanels[]. See routers/app_checks.py::
   *  get_check_scene()'s docstring on why. */
  panels: SceneMeshDto | null;
  /** Visual-only support-leg/rack geometry under flat-mounted panels
   *  (engine/panorama.py::_mounting_leg_mesh()) — never affects panel
   *  count, position or tilt, purely presentation. null when every
   *  panel sits flush enough to need none, or there's no panel array. */
  mounting: SceneMeshDto | null;
  panelCount: number;
  obstacles: SceneObstacleDto[];
  version: string | null;
}

export async function getCheckScene(checkId: string): Promise<SceneGeometry> {
  return apiFetch(`/app/checks/${checkId}/scene`);
}

// -----------------------------------------------------------------------------
// OBS-04 — obstacles detected on a roof and applied to its exclusions, for
// drawing over the satellite imagery.
//
// `detected` distinguishes "this roof genuinely has none" from "nothing has
// looked yet": obstacle detection needs an OPENAI_API_KEY, and without one
// the pipeline reports insufficient_data. Rendering an empty roof as "no
// obstacles" in that case would be a lie of omission.
// -----------------------------------------------------------------------------

// domain/assessment.py::ObstacleType — a fixed, real classification, not
// a free-text guess.
export type ObstacleType =
  | "water_tank"
  | "hvac_unit"
  | "chimney"
  | "existing_solar_panel"
  | "vent"
  | "antenna"
  | "other";

export interface RoofObstacle {
  id: string;
  polygon: { lat: number; lng: number }[];
  // Both null for an obstacle applied before these fields existed —
  // never guessed for an older row. `confidence` is also null for a
  // customer-marked obstacle: someone pointing at their own roof is a
  // statement, not a probabilistic detection.
  type: ObstacleType | null;
  confidence: number | null;
  /** Provenance only — "customer_marked" when the homeowner placed it,
   *  a detector/pipeline name otherwise. Deliberately NOT a visual
   *  distinction: the result page renders both identically. It exists so
   *  the marking screen knows which items that customer may remove. */
  source: string | null;
}

export interface RoofObstacles {
  detected: boolean;
  reason: string | null;
  obstacles: RoofObstacle[];
}

export async function getCheckObstacles(checkId: string): Promise<RoofObstacles> {
  return apiFetch(`/app/checks/${checkId}/obstacles`);
}

/** The customer marking something that's really on their roof. The tap
 *  point becomes a small square server-side (a fixed, documented default
 *  size — a tap is a point, not a traced outline) and is unioned into the
 *  site's exclusions through the same OBS-04 path a detected obstacle
 *  takes. Like a corrected boundary, the geometry is versioned at once
 *  but the numbers only move once completeCheck() re-runs the
 *  assessment. */
export async function markCheckObstacle(
  checkId: string,
  input: { type: ObstacleType; lat: number; lng: number }
): Promise<RoofObstacle> {
  return apiFetch(`/app/checks/${checkId}/obstacles`, { method: "POST", body: input });
}

/** Removes an obstacle the customer placed themselves. AI detections are
 *  reversed through the audited admin OBS-06 path, not here — the server
 *  rejects those with a 403. */
export async function unmarkCheckObstacle(checkId: string, obstacleId: string): Promise<void> {
  await apiFetch(`/app/checks/${checkId}/obstacles/${obstacleId}`, { method: "DELETE" });
}

// -----------------------------------------------------------------------------
// Enquiry — the customer's own act of turning a viewed feasibility result
// into something an admin needs to look at. Deliberately separate from
// completing the check itself: a customer can view a SUITABLE result
// without ever calling raiseEnquiry().
// -----------------------------------------------------------------------------

// Customer-safe vendor card — no contact/legal fields (phone, email,
// GST/PAN, address). "distance" is deliberately absent: no vendor has a
// lat/lng in this schema, so "nearby" is a real district/state match
// category, never a fabricated distanceKm.
export interface NearbyVendor {
  id: string;
  name: string;
  matchCategory: "same_district" | "same_state" | "other";
  region: string;
  verificationStatus: string;
  availability: boolean;
  // Dormant metric (nothing computes a real value for it) — kept for
  // backward compatibility, no longer rendered as a customer rating.
  // See averageRating/reviewCount below for the real thing.
  accuracyScore: number;
  certifications: string[];
  // Real customer reviews — null average (not 0) when reviewCount is 0,
  // so the UI can show "No reviews yet" instead of a fabricated score.
  averageRating: number | null;
  reviewCount: number;
  // Live workload — how busy/experienced this vendor currently is.
  activeJobs: number;
  jobsCompleted: number;
}

export async function listNearbyVendors(checkId: string): Promise<NearbyVendor[]> {
  return apiFetch(`/app/checks/${checkId}/vendors`);
}

export async function raiseEnquiry(checkId: string, input: { vendorId?: string } = {}): Promise<Site> {
  return apiFetch(`/app/checks/${checkId}/enquiry`, {
    method: "POST",
    body: { vendorId: input.vendorId },
  });
}

export interface VendorReview {
  id: string;
  vendorId: string;
  rating: number;
  comment: string | null;
  createdAt: string;
  reviewerName: string;
}

export async function submitVendorReview(
  checkId: string,
  input: { rating: number; comment?: string }
): Promise<VendorReview> {
  return apiFetch(`/app/checks/${checkId}/review`, {
    method: "POST",
    body: { rating: input.rating, comment: input.comment },
  });
}

export async function listVendorReviews(checkId: string, vendorId: string): Promise<VendorReview[]> {
  return apiFetch(`/app/checks/${checkId}/vendors/${vendorId}/reviews`);
}

// -----------------------------------------------------------------------------
// Installation projects — the post-quotation pipeline. Three audiences
// over the same four tables: the customer (accept the quotation, watch
// the stage, sign off at the end), the vendor crew doing the work, and
// the admin approving QC and commissioning.
// -----------------------------------------------------------------------------

/** The missing trigger the whole pipeline used to lack: nothing happened
 *  after an assessment was approved until the customer said yes. 409s if
 *  the assessment isn't approved, or if a project already exists. */
export async function acceptQuotation(checkId: string): Promise<CustomerInstallation> {
  return apiFetch(`/app/checks/${checkId}/accept-quotation`, { method: "POST" });
}

/** 404 when no project exists yet — callers treat that as "no install
 *  section to render", not as an error. */
export async function getCheckInstallation(checkId: string): Promise<CustomerInstallation> {
  return apiFetch(`/app/checks/${checkId}/installation`);
}

/** The customer's final handover sign-off. 409s until the vendor has
 *  submitted the commissioning record. */
export async function acceptInstallation(checkId: string): Promise<CommissioningRecord> {
  return apiFetch(`/app/checks/${checkId}/installation/accept`, { method: "POST" });
}

// --- vendor -----------------------------------------------------------------

export async function listVendorInstallations(
  params: { status?: string } = {}
): Promise<InstallationProject[]> {
  return apiFetch("/app/vendor/installations", { query: { ...params } });
}

export async function getVendorInstallation(projectId: string): Promise<InstallationProject> {
  return apiFetch(`/app/vendor/installations/${projectId}`);
}

export async function advanceVendorInstallationStatus(
  projectId: string,
  input: { status: string; panelModel?: string; inverterModel?: string }
): Promise<InstallationProject> {
  return apiFetch(`/app/vendor/installations/${projectId}/status`, { method: "PATCH", body: input });
}

export async function getVendorInstallationQc(projectId: string): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/vendor/installations/${projectId}/qc`);
}

export async function saveVendorInstallationQc(
  projectId: string,
  input: { checklist: InstallationQcItems; notes?: string | null }
): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/vendor/installations/${projectId}/qc`, { method: "PATCH", body: input });
}

/** Stamps submittedAt — the precondition for the admin's QC approval. */
export async function submitVendorInstallationQc(
  projectId: string,
  input: { checklist: InstallationQcItems; notes?: string | null }
): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/vendor/installations/${projectId}/qc/submit`, { method: "POST", body: input });
}

export async function listVendorInstallationPhotos(
  projectId: string,
  params: { stage?: string } = {}
): Promise<InstallationPhoto[]> {
  return apiFetch(`/app/vendor/installations/${projectId}/photos`, { query: { ...params } });
}

export async function addVendorInstallationPhoto(
  projectId: string,
  input: { stage: string; dataUrl: string; lat?: number | null; lng?: number | null }
): Promise<InstallationPhoto> {
  return apiFetch(`/app/vendor/installations/${projectId}/photos`, { method: "POST", body: input });
}

export async function getVendorCommissioning(projectId: string): Promise<CommissioningRecord> {
  return apiFetch(`/app/vendor/installations/${projectId}/commissioning`);
}

export async function submitVendorCommissioning(
  projectId: string,
  input: Partial<Omit<CommissioningRecord, "projectId" | "customerAccepted" | "vendorConfirmed" | "adminApproved">>
): Promise<CommissioningRecord> {
  return apiFetch(`/app/vendor/installations/${projectId}/commissioning`, {
    method: "POST",
    body: input,
  });
}

// --- admin ------------------------------------------------------------------

export async function listAdminInstallations(
  params: { status?: string } = {}
): Promise<InstallationProject[]> {
  return apiFetch("/app/admin/installations", { query: { ...params } });
}

export async function getAdminInstallation(projectId: string): Promise<InstallationProject> {
  return apiFetch(`/app/admin/installations/${projectId}`);
}

export async function setAdminInstallationStatus(
  projectId: string,
  input: { status: string; panelModel?: string; inverterModel?: string }
): Promise<InstallationProject> {
  return apiFetch(`/app/admin/installations/${projectId}/status`, { method: "PATCH", body: input });
}

export async function getAdminInstallationQc(projectId: string): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/admin/installations/${projectId}/qc`);
}

export async function saveAdminInstallationQc(
  projectId: string,
  input: { checklist: InstallationQcItems; notes?: string | null }
): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/admin/installations/${projectId}/qc`, { method: "PATCH", body: input });
}

export async function approveInstallationQc(projectId: string): Promise<InstallationQcChecklist> {
  return apiFetch(`/app/admin/installations/${projectId}/qc/approve`, { method: "POST" });
}

export async function listAdminInstallationPhotos(
  projectId: string,
  params: { stage?: string } = {}
): Promise<InstallationPhoto[]> {
  return apiFetch(`/app/admin/installations/${projectId}/photos`, { query: { ...params } });
}

export async function getAdminCommissioning(projectId: string): Promise<CommissioningRecord> {
  return apiFetch(`/app/admin/installations/${projectId}/commissioning`);
}

export async function saveAdminCommissioning(
  projectId: string,
  input: Partial<Omit<CommissioningRecord, "projectId" | "customerAccepted" | "vendorConfirmed" | "adminApproved">>
): Promise<CommissioningRecord> {
  return apiFetch(`/app/admin/installations/${projectId}/commissioning`, {
    method: "PATCH",
    body: input,
  });
}

/** The final gate — also what moves the project itself to "completed". */
export async function approveCommissioning(projectId: string): Promise<CommissioningRecord> {
  return apiFetch(`/app/admin/installations/${projectId}/commissioning/approve`, { method: "POST" });
}
