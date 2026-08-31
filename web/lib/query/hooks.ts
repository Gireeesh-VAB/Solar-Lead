"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api/client";
import type {
  AdminVendorListParams,
  AssessmentListParams,
  AuditLogListParams,
  NewCheckInput,
  SiteListParams,
  VendorJobListParams,
} from "@/lib/api/client";
import type { CustomerProfile } from "@/lib/fixtures/customer";

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

export function useOcrExtraction() {
  return useMutation({ mutationFn: (kind: "bill" | "payment_proof") => api.runOcrExtraction(kind) });
}

export function useSubmitUsn(siteId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { usn: string; method: "manual" | "bill_ocr" | "payment_proof_ocr" }) =>
      api.submitUsn(siteId, input.usn, input.method),
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

export function useAdminVendors(params: AdminVendorListParams = {}) {
  return useQuery({ queryKey: ["admin-vendors", params], queryFn: () => api.listAdminVendors(params) });
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["platform-health"] }),
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
