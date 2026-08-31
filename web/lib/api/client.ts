// -----------------------------------------------------------------------------
// Mock API client.
//
// Every function below simulates a network round trip against in-memory
// fixtures (200-600ms latency) and returns data shaped exactly like the
// planned FastAPI backend is expected to return it.
//
// TODO: replace with real fetch to NEXT_PUBLIC_API_BASE_URL
// When the backend exists, each function body becomes:
//   const res = await fetch(`${process.env.NEXT_PUBLIC_API_BASE_URL}/...`, opts);
//   if (!res.ok) throw new ApiError(...);
//   return res.json();
// The function signatures below (names, params, return types) are designed
// to stay stable across that swap so no calling code needs to change.
// -----------------------------------------------------------------------------

import { MOCK_SITES, getSiteById } from "@/lib/fixtures/sites";
import {
  MOCK_CALIBRATION,
  MOCK_COMPOSITES,
  MOCK_HISTORY,
  MOCK_IMPORT_JOBS,
  MOCK_JURISDICTIONS,
  MOCK_MODEL_VERSIONS,
} from "@/lib/fixtures/misc";
import { MOCK_VENDOR_JOBS, MOCK_VENDOR_PAYOUTS, MOCK_VENDOR_PROFILE, requirementsFor } from "@/lib/fixtures/vendor";
import { MOCK_ADMIN_VENDORS, MOCK_AUDIT_LOG, MOCK_PLATFORM_HEALTH } from "@/lib/fixtures/admin";
import { MOCK_CHECKS, MOCK_CUSTOMER, type CustomerProfile } from "@/lib/fixtures/customer";
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
  VendorVerificationStatus,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(message: string, public status = 500) {
    super(message);
  }
}

function latency(): number {
  return 200 + Math.random() * 400;
}

function delay<T>(value: T): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), latency()));
}

// In-memory mutable copies so the app can "write" during the session.
const sitesStore: Site[] = MOCK_SITES.map((s) => ({ ...s }));
const jobsStore: ImportJob[] = MOCK_IMPORT_JOBS.map((j) => ({ ...j }));
const calibrationStore: CalibrationProposal[] = MOCK_CALIBRATION.map((c) => ({ ...c }));
const modelStore: ModelVersionProposal[] = MOCK_MODEL_VERSIONS.map((m) => ({ ...m }));
const vendorJobsStore: VendorJob[] = MOCK_VENDOR_JOBS.map((j) => ({ ...j }));
const vendorPayoutsStore: PayoutEntry[] = MOCK_VENDOR_PAYOUTS.map((p) => ({ ...p }));
const vendorProfileStore: VendorProfile = { ...MOCK_VENDOR_PROFILE };
const adminVendorsStore: AdminVendorSummary[] = MOCK_ADMIN_VENDORS.map((v) => ({ ...v }));
const auditLogStore: AuditLogEntry[] = MOCK_AUDIT_LOG.map((a) => ({ ...a }));
const platformHealthStore: PlatformHealthMetric = {
  ...MOCK_PLATFORM_HEALTH,
  quotas: MOCK_PLATFORM_HEALTH.quotas.map((q) => ({ ...q })),
};
const checksStore: Site[] = MOCK_CHECKS.map((c) => ({ ...c }));
const customerProfileStore: CustomerProfile = { ...MOCK_CUSTOMER };

export interface SiteListParams {
  q?: string;
  siteType?: string;
  verdict?: string;
  state?: string;
  page?: number;
  pageSize?: number;
}

export async function listSites(params: SiteListParams = {}): Promise<{ items: Site[]; total: number }> {
  let items = sitesStore;
  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.address.toLowerCase().includes(q) ||
        s.district.toLowerCase().includes(q) ||
        s.id.toLowerCase().includes(q) ||
        (s.usn ?? "").toLowerCase().includes(q)
    );
  }
  if (params.siteType) items = items.filter((s) => s.siteType === params.siteType);
  if (params.verdict) items = items.filter((s) => s.latestAssessment?.verdict === params.verdict);
  if (params.state) items = items.filter((s) => s.state === params.state);
  const total = items.length;
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? total;
  const start = (page - 1) * pageSize;
  return delay({ items: items.slice(start, start + pageSize), total });
}

export async function getSite(siteId: string): Promise<Site> {
  const site = getSiteById(siteId) ?? sitesStore.find((s) => s.id === siteId);
  if (!site) throw new ApiError(`Site ${siteId} not found`, 404);
  return delay(site);
}

export async function getSiteHistory(siteId: string): Promise<HistoryEvent[]> {
  return delay(MOCK_HISTORY[siteId] ?? []);
}

export async function listImportJobs(): Promise<ImportJob[]> {
  return delay(jobsStore);
}

export async function getImportJob(jobId: string): Promise<ImportJob> {
  const job = jobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  return delay(job);
}

export async function listComposites(): Promise<CompositeSite[]> {
  return delay(MOCK_COMPOSITES);
}

export async function listCalibrationProposals(): Promise<CalibrationProposal[]> {
  return delay(calibrationStore);
}

export async function approveCalibrationProposal(id: string): Promise<CalibrationProposal> {
  const item = calibrationStore.find((c) => c.id === id);
  if (!item) throw new ApiError("Not found", 404);
  item.status = "approved";
  return delay(item);
}

export async function rejectCalibrationProposal(id: string): Promise<CalibrationProposal> {
  const item = calibrationStore.find((c) => c.id === id);
  if (!item) throw new ApiError("Not found", 404);
  item.status = "rejected";
  return delay(item);
}

export async function listModelVersions(): Promise<ModelVersionProposal[]> {
  return delay(modelStore);
}

export async function approveModelVersion(id: string): Promise<ModelVersionProposal> {
  const item = modelStore.find((m) => m.id === id);
  if (!item) throw new ApiError("Not found", 404);
  modelStore.forEach((m) => {
    if (m.modelName === item.modelName && m.status === "active") m.status = "rejected";
  });
  item.status = "active";
  return delay(item);
}

export async function rejectModelVersion(id: string): Promise<ModelVersionProposal> {
  const item = modelStore.find((m) => m.id === id);
  if (!item) throw new ApiError("Not found", 404);
  item.status = "rejected";
  return delay(item);
}

export async function listJurisdictions(): Promise<JurisdictionConstraintPack[]> {
  return delay(MOCK_JURISDICTIONS);
}

export async function submitUsn(siteId: string, usn: string, method: "manual" | "bill_ocr" | "payment_proof_ocr"): Promise<Site> {
  const site = sitesStore.find((s) => s.id === siteId);
  if (!site) throw new ApiError("Not found", 404);
  site.usn = usn;
  site.usnStatus = "confirmed";
  void method;
  return delay(site);
}

export interface OcrResult {
  extractedUsn: string;
  confidence: number;
  sourceLabel: string;
}

export async function runOcrExtraction(kind: "bill" | "payment_proof"): Promise<OcrResult> {
  return delay({
    extractedUsn: `USN${Math.floor(100000000 + Math.random() * 899999999)}`,
    confidence: kind === "bill" ? 0.91 : 0.86,
    sourceLabel: kind === "bill" ? "Electricity bill (uploaded scan)" : "Payment proof (uploaded scan)",
  });
}

export async function saveBoundary(siteId: string, points: { lat: number; lng: number }[]): Promise<Site> {
  const site = sitesStore.find((s) => s.id === siteId);
  if (!site) throw new ApiError("Not found", 404);
  site.boundary = points;
  return delay(site);
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
  const newSite: Site = {
    id: `ST-${(2000 + sitesStore.length).toString()}`,
    name: input.name,
    siteType: input.siteType,
    address: input.address,
    district: input.district,
    state: input.state,
    location: { lat: input.lat, lng: input.lng },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    latestAssessment: null,
    usnStatus: input.siteType === "ROOFTOP_RESIDENTIAL" || input.siteType === "ROOFTOP_CI" ? "not_started" : undefined,
    usn: null,
    tags: ["new"],
  };
  sitesStore.unshift(newSite);
  return delay(newSite);
}

export interface PortfolioSummary {
  totalSites: number;
  totalCapacityKwp: number;
  verdictBreakdown: Record<string, number>;
  activeJobs: number;
  siteTypeBreakdown: Record<string, number>;
}

export async function getPortfolioSummary(): Promise<PortfolioSummary> {
  const verdictBreakdown: Record<string, number> = {};
  const siteTypeBreakdown: Record<string, number> = {};
  let totalCapacityKwp = 0;
  for (const s of sitesStore) {
    const v = s.latestAssessment?.verdict ?? "INSUFFICIENT_DATA";
    verdictBreakdown[v] = (verdictBreakdown[v] ?? 0) + 1;
    siteTypeBreakdown[s.siteType] = (siteTypeBreakdown[s.siteType] ?? 0) + 1;
    totalCapacityKwp += s.latestAssessment?.capacityKwp ?? 0;
  }
  return delay({
    totalSites: sitesStore.length,
    totalCapacityKwp,
    verdictBreakdown,
    activeJobs: jobsStore.filter((j) => j.status === "running" || j.status === "queued").length,
    siteTypeBreakdown,
  });
}

// -----------------------------------------------------------------------------
// Vendor portal
// -----------------------------------------------------------------------------

export interface VendorJobListParams {
  status?: string;
  sort?: "deadline" | "distance" | "payout";
}

export async function listVendorJobs(params: VendorJobListParams = {}): Promise<VendorJob[]> {
  let items = vendorJobsStore;
  if (params.status) items = items.filter((j) => j.status === params.status);
  items = [...items];
  if (params.sort === "distance") items.sort((a, b) => a.distanceKm - b.distanceKm);
  else if (params.sort === "payout") items.sort((a, b) => b.payoutInr - a.payoutInr);
  else if (params.sort === "deadline") items.sort((a, b) => new Date(a.deadline).getTime() - new Date(b.deadline).getTime());
  return delay(items);
}

export async function getVendorJob(jobId: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  return delay(job);
}

export async function acceptVendorJob(jobId: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  job.status = "accepted";
  return delay(job);
}

export async function declineVendorJob(jobId: string): Promise<VendorJob> {
  const idx = vendorJobsStore.findIndex((j) => j.id === jobId);
  if (idx === -1) throw new ApiError(`Job ${jobId} not found`, 404);
  const [job] = vendorJobsStore.splice(idx, 1);
  return delay(job);
}

export async function startVendorJob(jobId: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  job.status = "in_progress";
  return delay(job);
}

export async function submitVendorJob(jobId: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  job.status = "submitted";
  job.submittedAt = new Date().toISOString();
  return delay(job);
}

export async function uploadPanoramaPhoto(jobId: string, dataUrl: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  job.panoramaPhotoDataUrl = dataUrl;
  return delay(job);
}

export async function saveShadingNotes(jobId: string, notes: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === jobId);
  if (!job) throw new ApiError(`Job ${jobId} not found`, 404);
  job.shadingNotes = notes;
  return delay(job);
}

export async function getVendorProfile(): Promise<VendorProfile> {
  return delay(vendorProfileStore);
}

export async function updateVendorAvailability(available: boolean): Promise<VendorProfile> {
  vendorProfileStore.availability = available;
  return delay(vendorProfileStore);
}

export async function listVendorPayouts(): Promise<PayoutEntry[]> {
  return delay(vendorPayoutsStore);
}

export interface VendorEarningsSummary {
  weekTotalInr: number;
  pendingInr: number;
  paidInr: number;
  disputedInr: number;
  jobsCompletedThisWeek: number;
}

export async function getVendorEarningsSummary(): Promise<VendorEarningsSummary> {
  const pendingInr = vendorPayoutsStore.filter((p) => p.status === "pending").reduce((sum, p) => sum + p.amount, 0);
  const paidInr = vendorPayoutsStore.filter((p) => p.status === "paid").reduce((sum, p) => sum + p.amount, 0);
  const disputedInr = vendorPayoutsStore.filter((p) => p.status === "disputed").reduce((sum, p) => sum + p.amount, 0);
  const weekAgo = Date.now() - 7 * 86400000;
  const recent = vendorPayoutsStore.filter((p) => new Date(p.date).getTime() >= weekAgo);
  return delay({
    weekTotalInr: recent.reduce((sum, p) => sum + p.amount, 0),
    pendingInr,
    paidInr,
    disputedInr,
    jobsCompletedThisWeek: recent.length,
  });
}

export async function listVendorSubmissions(): Promise<VendorJob[]> {
  return delay(vendorJobsStore.filter((j) => j.status === "submitted"));
}

export async function disputeSubmission(id: string, reason: string): Promise<VendorJob> {
  const job = vendorJobsStore.find((j) => j.id === id);
  if (!job) throw new ApiError(`Job ${id} not found`, 404);
  job.disputeStatus = "open";
  job.disputeReason = reason;
  return delay(job);
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
  let items = adminVendorsStore;
  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter((v) => v.name.toLowerCase().includes(q) || v.serviceArea.toLowerCase().includes(q));
  }
  if (params.verificationStatus) items = items.filter((v) => v.verificationStatus === params.verificationStatus);
  items = [...items];
  if (params.sort === "accuracy") items.sort((a, b) => b.accuracyScore - a.accuracyScore);
  else if (params.sort === "sla") items.sort((a, b) => b.slaCompliancePct - a.slaCompliancePct);
  return delay(items);
}

export async function getAdminVendor(id: string): Promise<AdminVendorSummary> {
  const vendor = adminVendorsStore.find((v) => v.id === id);
  if (!vendor) throw new ApiError(`Vendor ${id} not found`, 404);
  return delay(vendor);
}

export async function suspendVendor(id: string): Promise<AdminVendorSummary> {
  const vendor = adminVendorsStore.find((v) => v.id === id);
  if (!vendor) throw new ApiError(`Vendor ${id} not found`, 404);
  vendor.verificationStatus = "suspended";
  return delay(vendor);
}

export async function reinstateVendor(id: string): Promise<AdminVendorSummary> {
  const vendor = adminVendorsStore.find((v) => v.id === id);
  if (!vendor) throw new ApiError(`Vendor ${id} not found`, 404);
  vendor.verificationStatus = "verified";
  return delay(vendor);
}

export async function listVendorVerificationQueue(): Promise<AdminVendorSummary[]> {
  return delay(adminVendorsStore.filter((v) => v.verificationStatus === "pending"));
}

export async function approveVendorVerification(id: string): Promise<AdminVendorSummary> {
  const vendor = adminVendorsStore.find((v) => v.id === id);
  if (!vendor) throw new ApiError(`Vendor ${id} not found`, 404);
  vendor.verificationStatus = "verified";
  return delay(vendor);
}

export async function rejectVendorVerification(id: string): Promise<AdminVendorSummary> {
  const vendor = adminVendorsStore.find((v) => v.id === id);
  if (!vendor) throw new ApiError(`Vendor ${id} not found`, 404);
  vendor.verificationStatus = "rejected";
  return delay(vendor);
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

export async function listAllAssessments(
  params: AssessmentListParams = {}
): Promise<{ items: AdminAssessmentRow[]; total: number }> {
  let items: AdminAssessmentRow[] = sitesStore
    .filter((s) => s.latestAssessment)
    .map((s) => ({
      siteId: s.id,
      siteName: s.name,
      district: s.district,
      state: s.state,
      assessment: s.latestAssessment as Assessment,
    }));
  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter(
      (row) =>
        row.siteName.toLowerCase().includes(q) ||
        row.siteId.toLowerCase().includes(q) ||
        row.district.toLowerCase().includes(q)
    );
  }
  if (params.verdict) items = items.filter((row) => row.assessment.verdict === params.verdict);
  const total = items.length;
  const page = params.page ?? 1;
  const pageSize = params.pageSize ?? total;
  const start = (page - 1) * pageSize;
  return delay({ items: items.slice(start, start + pageSize), total });
}

export interface AuditLogListParams {
  actor?: string;
  action?: string;
  q?: string;
}

export async function listAuditLog(params: AuditLogListParams = {}): Promise<AuditLogEntry[]> {
  let items = auditLogStore;
  if (params.actor) items = items.filter((a) => a.actor === params.actor);
  if (params.action) items = items.filter((a) => a.action === params.action);
  if (params.q) {
    const q = params.q.toLowerCase();
    items = items.filter(
      (a) =>
        a.actor.toLowerCase().includes(q) ||
        a.action.toLowerCase().includes(q) ||
        a.target.toLowerCase().includes(q) ||
        a.details.toLowerCase().includes(q)
    );
  }
  return delay(items);
}

export async function getPlatformHealth(): Promise<PlatformHealthMetric> {
  return delay(platformHealthStore);
}

export async function rotateApiKey(service: string): Promise<{ service: string; rotatedAt: string }> {
  void service;
  return delay({ service, rotatedAt: new Date().toISOString() });
}

// -----------------------------------------------------------------------------
// Customer portal (consumer self-service: signup -> point a location -> result)
//
// A "check" is the same shape as a Site with a latestAssessment — this simply
// exposes that model through a simpler, homeowner-facing set of endpoints.
// -----------------------------------------------------------------------------

export async function listChecks(): Promise<Site[]> {
  const items = [...checksStore].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  return delay(items);
}

export async function getCheck(checkId: string): Promise<Site> {
  const check = checksStore.find((c) => c.id === checkId);
  if (!check) throw new ApiError(`Check ${checkId} not found`, 404);
  return delay(check);
}

export interface NewCheckInput {
  address: string;
  lat: number;
  lng: number;
  siteType?: SiteType;
}

export async function createCheck(input: NewCheckInput): Promise<Site> {
  const newCheck: Site = {
    id: `CHK-${Date.now().toString(36).toUpperCase()}`,
    name: input.address || "New location",
    siteType: input.siteType ?? "ROOFTOP_RESIDENTIAL",
    address: input.address || "Pinned location",
    district: "",
    state: "",
    location: { lat: input.lat, lng: input.lng },
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    latestAssessment: null,
    tags: [],
  };
  checksStore.unshift(newCheck);
  return delay(newCheck);
}

const CHECK_VERDICT_POOL: Verdict[] = [
  "SUITABLE",
  "SUITABLE",
  "SUITABLE_SUBJECT_TO_SURVEY",
  "CONDITIONAL",
  "INSUFFICIENT_DATA",
  "NOT_SUITABLE",
];

const CHECK_PLAIN_CONSTRAINT: Record<Verdict, BindingConstraint | null> = {
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

const CHECK_PLAIN_REASONS: Record<Verdict, string[]> = {
  SUITABLE: ["Enough clear space for a solar system.", "No blockers found nearby."],
  SUITABLE_SUBJECT_TO_SURVEY: ["Looks good from imagery.", "A quick in-person check will confirm it."],
  CONDITIONAL: ["The location can support solar.", "A connection upgrade step is needed first."],
  INSUFFICIENT_DATA: ["The available imagery isn't clear enough yet.", "This is a data gap, not a rejection."],
  NOT_SUITABLE: ["Not enough usable space at this exact spot.", "Shading or layout rules it out for now."],
};

function generateCheckAssessment(check: Site): Assessment {
  const verdict = CHECK_VERDICT_POOL[Math.floor(Math.random() * CHECK_VERDICT_POOL.length)];
  const confidence: ConfidenceTier = verdict === "INSUFFICIENT_DATA" ? "N/A" : verdict === "SUITABLE" ? "High" : "Medium";
  const capacityKwp = verdict === "NOT_SUITABLE" || verdict === "INSUFFICIENT_DATA" ? 0 : Number((2.5 + Math.random() * 7).toFixed(1));
  return {
    id: `AS-${check.id}`,
    siteId: check.id,
    verdict,
    capacityKwp,
    confidence,
    bindingConstraint: CHECK_PLAIN_CONSTRAINT[verdict],
    reasons: CHECK_PLAIN_REASONS[verdict],
    ceilingLedger: [],
    panoramaUrl: null,
    mlSuitabilityScore: verdict === "INSUFFICIENT_DATA" ? null : Number((0.6 + Math.random() * 0.35).toFixed(2)),
    generation:
      verdict === "NOT_SUITABLE" || verdict === "INSUFFICIENT_DATA"
        ? undefined
        : { p50AnnualKwh: Math.round(capacityKwp * 1450), p90AnnualKwh: Math.round(capacityKwp * 1280) },
    cache: { cacheHit: false },
    assessedAt: new Date().toISOString(),
    modelVersion: "fitness-core-v2.4.0",
  };
}

// A check whose verdict comes back "subject to survey" can't be booked with
// confidence from imagery alone — it needs a vendor on-site to confirm the
// roof, capture the boundary, and note anything the imagery missed. This is
// the customer-check -> vendor-job handoff: the trigger point where a
// generated lead actually reaches a vendor's queue.
function createVendorJobFromCheck(check: Site): VendorJob {
  return {
    id: `JOB-${check.id}`,
    siteId: check.id,
    siteName: check.name,
    siteType: check.siteType,
    district: check.district || "Unassigned",
    state: check.state || "Unassigned",
    deadline: new Date(Date.now() + 3 * 86400000).toISOString(),
    payoutInr: Math.max(800, Math.round((check.latestAssessment?.capacityKwp ?? 3) * 350)),
    status: "queued",
    assignedAt: new Date().toISOString(),
    requirements: requirementsFor(check.siteType),
    distanceKm: Number((5 + Math.random() * 25).toFixed(1)),
    estimatedCapacityKwp: check.latestAssessment?.capacityKwp,
  };
}

export async function completeCheck(checkId: string): Promise<Site> {
  const check = checksStore.find((c) => c.id === checkId);
  if (!check) throw new ApiError(`Check ${checkId} not found`, 404);
  check.latestAssessment = generateCheckAssessment(check);
  check.updatedAt = new Date().toISOString();

  if (check.latestAssessment.verdict === "SUITABLE_SUBJECT_TO_SURVEY") {
    vendorJobsStore.unshift(createVendorJobFromCheck(check));
  }

  return delay(check);
}

export async function getCustomerProfile(): Promise<CustomerProfile> {
  return delay(customerProfileStore);
}

export async function updateCustomerProfile(input: Partial<CustomerProfile>): Promise<CustomerProfile> {
  Object.assign(customerProfileStore, input);
  return delay(customerProfileStore);
}
