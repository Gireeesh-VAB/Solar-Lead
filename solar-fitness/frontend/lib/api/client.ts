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
  CompositeSite,
  ConfidenceTier,
  HistoryEvent,
  ImportJob,
  JurisdictionConstraintPack,
  ModelVersionProposal,
  PayoutEntry,
  PlatformHealthMetric,
  Site,
  SiteType,
  Verdict,
  VendorJob,
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

export async function getVendorProfile(): Promise<VendorProfile> {
  return apiFetch("/app/vendor/profile");
}

export async function updateVendorAvailability(available: boolean): Promise<VendorProfile> {
  return apiFetch("/app/vendor/profile/availability", { method: "PATCH", body: { available } });
}

export async function listVendorPayouts(): Promise<PayoutEntry[]> {
  return apiFetch("/app/vendor/payouts");
}

export interface VendorEarningsSummary {
  weekTotalInr: number;
  pendingInr: number;
  paidInr: number;
  disputedInr: number;
  jobsCompletedThisWeek: number;
}

export async function getVendorEarningsSummary(): Promise<VendorEarningsSummary> {
  return apiFetch("/app/vendor/earnings-summary");
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

export interface AdminAssessmentRow {
  siteId: string;
  siteName: string;
  district: string;
  state: string;
  assessment: Assessment;
}

export interface AssessmentListParams {
  q?: string;
  verdict?: string;
  page?: number;
  pageSize?: number;
}

// The backend's admin listing has no server-side search/pagination (just
// limit/offset) and doesn't join site name/district/state — it only has
// site_id. Fetch a generous page, then filter/paginate client-side the same
// way the mock always did; siteName falls back to siteId (honest — this
// endpoint has no site name to give) and district/state are empty.
interface RawCapacityResult {
  recommended_kwp: number | null;
}

interface RawAdminAssessment {
  id: string;
  siteId: string;
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
}

function toAdminAssessmentRow(raw: RawAdminAssessment): AdminAssessmentRow {
  return {
    siteId: raw.siteId,
    siteName: raw.siteId,
    district: "",
    state: "",
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
      cache: { cacheHit: raw.cacheHit },
      assessedAt: raw.createdAt,
      modelVersion: raw.engineVersion,
    },
  };
}

export async function listAllAssessments(
  params: AssessmentListParams = {}
): Promise<{ items: AdminAssessmentRow[]; total: number }> {
  const raw = await apiFetch<RawAdminAssessment[]>("/app/admin/assessments", { query: { limit: 500, offset: 0 } });
  let items = raw.map(toAdminAssessmentRow);

  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter((row) => row.siteId.toLowerCase().includes(q));
  }
  if (params.verdict) items = items.filter((row) => row.assessment.verdict === params.verdict);

  const total = items.length;
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? total;
  const start = (page - 1) * pageSize;
  return { items: items.slice(start, start + pageSize), total };
}

export interface AuditLogListParams {
  actor?: string;
  action?: string;
  q?: string;
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

export interface NewCheckInput {
  address: string;
  lat: number;
  lng: number;
  siteType?: SiteType;
  /** CON-05 input. Optional — omitting them sizes the system by roof area
   *  alone, which is what every check did before bills could be captured. */
  monthlyBillLowInr?: number;
  monthlyBillHighInr?: number;
}

export async function createCheck(input: NewCheckInput): Promise<Site> {
  return apiFetch("/app/checks", { method: "POST", body: input });
}

export async function completeCheck(checkId: string): Promise<Site> {
  return apiFetch(`/app/checks/${checkId}/complete`, { method: "POST" });
}

export async function getCustomerProfile(): Promise<CustomerProfile> {
  return apiFetch("/app/customer/profile");
}

export async function updateCustomerProfile(input: Partial<CustomerProfile>): Promise<CustomerProfile> {
  return apiFetch("/app/customer/profile", { method: "PATCH", body: input });
}

// -----------------------------------------------------------------------------
// Google's real per-panel solar layout for a check's rooftop, for drawing
// over the satellite imagery.
//
// Deliberately its OWN endpoint rather than a field on the check: it costs
// a Solar API call, it is presentation-only, and a failure must never take
// the result page's verdict or capacity down with it.
//
// panelCount/totalKwp here describe GOOGLE'S layout. They are not P2's
// recommendation and the two genuinely disagree — never present them as
// one number.
// -----------------------------------------------------------------------------

export interface SolarPanelPolygonDto {
  corners: { lat: number; lng: number }[];
  capacityWatts: number | null;
  orientation: string;
  segmentIndex: number | null;
  azimuthDegrees: number | null;
  pitchDegrees: number | null;
}

export interface SolarLayout {
  status: "ok" | "no_coverage" | "no_layout" | "error";
  reason: string | null;
  source: string;
  panelCount: number;
  totalKwp: number;
  panels: SolarPanelPolygonDto[];
}

export async function getCheckSolarLayout(checkId: string): Promise<SolarLayout> {
  return apiFetch(`/app/checks/${checkId}/solar-layout`);
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

export interface RoofObstacle {
  id: string;
  polygon: { lat: number; lng: number }[];
}

export interface RoofObstacles {
  detected: boolean;
  reason: string | null;
  obstacles: RoofObstacle[];
}

export async function getCheckObstacles(checkId: string): Promise<RoofObstacles> {
  return apiFetch(`/app/checks/${checkId}/obstacles`);
}
