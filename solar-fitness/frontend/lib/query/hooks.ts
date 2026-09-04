"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api/client";
import type {
  AdminVendorListParams,
  AssessmentListParams,
  AuditLogListParams,
  FinancialFeasibility,
  GridFeasibility,
  NewCheckInput,
  NewVendorInput,
  SiteListParams,
  VendorJobListParams,
} from "@/lib/api/client";
import type { CustomerProfile } from "@/lib/fixtures/customer";
import type {
  BatteryAssessment,
  ElectricalAssessment,
  InstallationConstraints,
  ObstacleSurveyItem,
  SafetyAssessment,
  StructuralAssessment,
} from "@/lib/types";

export function useSites(params: SiteListParams = {}) {
  return useQuery({
    queryKey: ["sites", params],
    queryFn: () => api.listSites(params),
  });
}

export function useSite(siteId: string) {
  return useQuery({
    queryKey: ["site", siteId],
    queryFn: () => api.getSite(siteId),
  });
}

export function useSiteHistory(siteId: string) {
  return useQuery({
    queryKey: ["site-history", siteId],
    queryFn: () => api.getSiteHistory(siteId),
  });
}

export function usePortfolioSummary() {
  return useQuery({ queryKey: ["portfolio-summary"], queryFn: api.getPortfolioSummary });
}

export function useImportJobs() {
  return useQuery({ queryKey: ["import-jobs"], queryFn: api.listImportJobs });
}

export function useImportJob(jobId: string) {
  return useQuery({
    queryKey: ["import-job", jobId],
    queryFn: () => api.getImportJob(jobId),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 4000 : false),
  });
}

export function useComposites() {
  return useQuery({ queryKey: ["composites"], queryFn: api.listComposites });
}

export function useCalibrationProposals() {
  return useQuery({ queryKey: ["calibration"], queryFn: api.listCalibrationProposals });
}

export function useCalibrationDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; decision: "approve" | "reject" }) =>
      input.decision === "approve" ? api.approveCalibrationProposal(input.id) : api.rejectCalibrationProposal(input.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["calibration"] }),
  });
}

export function useModelVersions() {
  return useQuery({ queryKey: ["model-versions"], queryFn: api.listModelVersions });
}

export function useModelVersionDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; decision: "approve" | "reject" }) =>
      input.decision === "approve" ? api.approveModelVersion(input.id) : api.rejectModelVersion(input.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["model-versions"] }),
  });
}

export function useJurisdictions() {
  return useQuery({ queryKey: ["jurisdictions"], queryFn: api.listJurisdictions });
}

export function useCaptureManualUsn(siteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (usn: string) => api.captureManualUsn(siteId, usn),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site", siteId] }),
  });
}

export function useExtractUsn(siteId: string) {
  return useMutation({
    mutationFn: (input: { kind: "bill" | "payment_proof"; file: File }) =>
      input.kind === "bill" ? api.extractUsnFromBill(siteId, input.file) : api.extractUsnFromPaymentProof(siteId, input.file),
  });
}

export function useConfirmUsn(siteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { uploadId: string; confirmedUsn: string }) => api.confirmUsn(siteId, input.uploadId, input.confirmedUsn),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site", siteId] }),
  });
}

export function useCreateSite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createSite,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sites"] }),
  });
}

export function useSaveBoundary(siteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (points: { lat: number; lng: number }[]) => api.saveBoundary(siteId, points),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["site", siteId] }),
  });
}

// -----------------------------------------------------------------------------
// Vendor portal
// -----------------------------------------------------------------------------

export function useVendorJobs(params: VendorJobListParams = {}) {
  return useQuery({
    queryKey: ["vendor-jobs", params],
    queryFn: () => api.listVendorJobs(params),
  });
}

export function useVendorJob(jobId: string) {
  return useQuery({
    queryKey: ["vendor-job", jobId],
    queryFn: () => api.getVendorJob(jobId),
  });
}

export function useUploadPanoramaPhoto(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (dataUrl: string) => api.uploadPanoramaPhoto(jobId, dataUrl),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveShadingNotes(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (notes: string) => api.saveShadingNotes(jobId, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveObstacleSurvey(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (obstacles: ObstacleSurveyItem[]) => api.saveObstacleSurvey(jobId, obstacles),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveStructuralAssessment(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessment: StructuralAssessment) =>
      api.saveStructuralAssessment(jobId, assessment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveElectricalAssessment(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessment: ElectricalAssessment) => api.saveElectricalAssessment(jobId, assessment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveInstallationConstraints(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (constraints: InstallationConstraints) => api.saveInstallationConstraints(jobId, constraints),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveSafetyAssessment(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessment: SafetyAssessment) => api.saveSafetyAssessment(jobId, assessment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useSaveBatteryAssessment(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (assessment: BatteryAssessment) => api.saveBatteryAssessment(jobId, assessment),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
    },
  });
}

export function useVendorJobAction(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "accept" | "decline" | "start" | "submit") => {
      if (action === "accept") return api.acceptVendorJob(jobId);
      if (action === "decline") return api.declineVendorJob(jobId);
      if (action === "start") return api.startVendorJob(jobId);
      return api.submitVendorJob(jobId);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", jobId] });
      qc.invalidateQueries({ queryKey: ["vendor-jobs"] });
      qc.invalidateQueries({ queryKey: ["vendor-submissions"] });
    },
  });
}

export function useVendorProfile() {
  return useQuery({ queryKey: ["vendor-profile"], queryFn: api.getVendorProfile });
}

export function useUpdateVendorAvailability() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (available: boolean) => api.updateVendorAvailability(available),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vendor-profile"] }),
  });
}

export function useVendorPayouts() {
  return useQuery({ queryKey: ["vendor-payouts"], queryFn: api.listVendorPayouts });
}

export function useVendorEarningsSummary() {
  return useQuery({ queryKey: ["vendor-earnings-summary"], queryFn: api.getVendorEarningsSummary });
}

export function useVendorSubmissions() {
  return useQuery({ queryKey: ["vendor-submissions"], queryFn: api.listVendorSubmissions });
}

export function useDisputeSubmission(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => api.disputeSubmission(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-job", id] });
      qc.invalidateQueries({ queryKey: ["vendor-submissions"] });
    },
  });
}

// -----------------------------------------------------------------------------
// Super admin portal
// -----------------------------------------------------------------------------

export function useAdminVendors(params: AdminVendorListParams = {}, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["admin-vendors", params],
    queryFn: () => api.listAdminVendors(params),
    enabled: options.enabled,
  });
}

export function useAdminVendor(id: string) {
  return useQuery({ queryKey: ["admin-vendor", id], queryFn: () => api.getAdminVendor(id) });
}

export function useAdminVendorStatusAction(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (action: "suspend" | "reinstate") =>
      action === "suspend" ? api.suspendVendor(id) : api.reinstateVendor(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-vendor", id] });
      qc.invalidateQueries({ queryKey: ["admin-vendors"] });
    },
  });
}

export function useVendorVerificationQueue() {
  return useQuery({ queryKey: ["vendor-verification-queue"], queryFn: api.listVendorVerificationQueue });
}

export function useVendorVerificationDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { id: string; decision: "approve" | "reject" }) =>
      input.decision === "approve" ? api.approveVendorVerification(input.id) : api.rejectVendorVerification(input.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-verification-queue"] });
      qc.invalidateQueries({ queryKey: ["admin-vendors"] });
    },
  });
}

export function useAllAssessments(params: AssessmentListParams = {}) {
  return useQuery({ queryKey: ["all-assessments", params], queryFn: () => api.listAllAssessments(params) });
}

export function useAdminAssessment(id: string) {
  return useQuery({ queryKey: ["admin-assessment", id], queryFn: () => api.getAdminAssessment(id) });
}

export function useApproveAssessment(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { vendorId: string; deadlineDays?: number; payoutInr?: number }) =>
      api.approveAssessment(id, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-assessment", id] });
      qc.invalidateQueries({ queryKey: ["all-assessments"] });
      qc.invalidateQueries({ queryKey: ["admin-vendors"] });
    },
  });
}

export function useRejectAssessment(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason: string) => api.rejectAssessment(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-assessment", id] });
      qc.invalidateQueries({ queryKey: ["all-assessments"] });
    },
  });
}

export function useSaveGridFeasibility(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (feasibility: GridFeasibility) => api.saveGridFeasibility(id, feasibility),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-assessment", id] });
      qc.invalidateQueries({ queryKey: ["all-assessments"] });
    },
  });
}

export function useSaveFinancialFeasibility(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (feasibility: FinancialFeasibility) => api.saveFinancialFeasibility(id, feasibility),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-assessment", id] });
      qc.invalidateQueries({ queryKey: ["all-assessments"] });
    },
  });
}

export function useAuditLog(params: AuditLogListParams = {}) {
  return useQuery({ queryKey: ["audit-log", params], queryFn: () => api.listAuditLog(params) });
}

export function usePlatformHealth() {
  return useQuery({ queryKey: ["platform-health"], queryFn: api.getPlatformHealth });
}

export function useRotateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (service: string) => api.rotateApiKey(service),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["platform-health"] });
      qc.invalidateQueries({ queryKey: ["service-api-keys"] });
    },
  });
}

export function useServiceApiKeys() {
  return useQuery({ queryKey: ["service-api-keys"], queryFn: api.listServiceApiKeys });
}

export function useFeatureFlags() {
  return useQuery({ queryKey: ["feature-flags"], queryFn: api.listFeatureFlags });
}

export function useSetFeatureFlag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { key: string; enabled: boolean }) => api.setFeatureFlag(input.key, input.enabled),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feature-flags"] }),
  });
}

export function useCreateAdminVendor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: NewVendorInput) => api.createAdminVendor(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-vendors"] }),
  });
}

export function useAdminVendorJobs(vendorId: string) {
  return useQuery({ queryKey: ["admin-vendor-jobs", vendorId], queryFn: () => api.listAdminVendorJobs(vendorId) });
}

export function useAdminVendorPayouts(vendorId: string) {
  return useQuery({
    queryKey: ["admin-vendor-payouts", vendorId],
    queryFn: () => api.listAdminVendorPayouts(vendorId),
  });
}

export function usePublishJurisdiction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (pack: string) => api.publishJurisdiction(pack),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jurisdictions"] }),
  });
}

// -----------------------------------------------------------------------------
// Customer portal
// -----------------------------------------------------------------------------

export function useChecks() {
  return useQuery({ queryKey: ["checks"], queryFn: api.listChecks });
}

export function useCheck(checkId: string) {
  return useQuery({ queryKey: ["check", checkId], queryFn: () => api.getCheck(checkId) });
}

/** Google's panel layout for a check's rooftop. Kept out of useCheck() so
 *  a slow or failing Solar API call never delays the result itself — the
 *  map and the analysis render first, panels arrive when they arrive. */
export function useCheckSolarLayout(checkId: string) {
  return useQuery({
    queryKey: ["check", checkId, "solar-layout"],
    queryFn: () => api.getCheckSolarLayout(checkId),
    // The layout is a property of the building, not of this page view.
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

/** Rooftop obstacles for a check. Separate from useCheck() for the same
 *  reason as the solar layout: it is presentation detail, and a slow or
 *  absent answer must never hold up the result itself. */
export function useCheckObstacles(checkId: string) {
  return useQuery({
    queryKey: ["check", checkId, "obstacles"],
    queryFn: () => api.getCheckObstacles(checkId),
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

export function useCreateCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: NewCheckInput) => api.createCheck(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["checks"] }),
  });
}

export function useCompleteCheck(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.completeCheck(checkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check", checkId] });
      qc.invalidateQueries({ queryKey: ["checks"] });
    },
  });
}

export function useCustomerProfile() {
  return useQuery({ queryKey: ["customer-profile"], queryFn: api.getCustomerProfile });
}

export function useUpdateCustomerProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: Partial<CustomerProfile>) => api.updateCustomerProfile(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["customer-profile"] }),
  });
}
