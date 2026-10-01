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
  CommissioningRecord,
  ElectricalAssessment,
  InstallationConstraints,
  InstallationQcItems,
  ObstacleSurveyItem,
  SafetyAssessment,
  StructuralAssessment,
} from "@/lib/types";

/** The writable slice of a commissioning record — the three sign-off
 *  flags are never sent by a form, each is set by its own endpoint. */
type CommissioningInput = Partial<
  Omit<CommissioningRecord, "projectId" | "customerAccepted" | "vendorConfirmed" | "adminApproved">
>;

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

export function useSubmitFieldBoundary(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (points: { lat: number; lng: number }[]) => api.submitFieldBoundary(jobId, points),
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

export function useVendorNotificationPreferences() {
  return useQuery({
    queryKey: ["vendor-notification-preferences"],
    queryFn: api.getVendorNotificationPreferences,
  });
}

export function useUpdateVendorNotificationPreferences() {
  const qc = useQueryClient();
  const queryKey = ["vendor-notification-preferences"];
  return useMutation({
    mutationFn: api.updateVendorNotificationPreferences,
    // Toggling a switch has to feel instant — waiting on the round trip
    // before the knob moves is what made these read as broken/laggy.
    // Apply the new value to the cache immediately and only roll back if
    // the request actually fails.
    onMutate: async (next) => {
      await qc.cancelQueries({ queryKey });
      const previous = qc.getQueryData(queryKey);
      qc.setQueryData(queryKey, next);
      return { previous };
    },
    onError: (_err, _next, context) => {
      if (context?.previous) qc.setQueryData(queryKey, context.previous);
    },
    onSettled: () => qc.invalidateQueries({ queryKey }),
  });
}

export function useChangePassword() {
  return useMutation({ mutationFn: api.changePassword });
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

export function useReassignAssessment(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { vendorId: string; deadlineDays?: number; reason?: string }) =>
      api.reassignAssessment(id, input),
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

/** FIN-02 admin config — the versioned financial-projection assumptions
 *  (escalation, export rate, self-consumption default, maintenance,
 *  financing defaults). Every PATCH creates a NEW version server-side
 *  (never edits one in place), so invalidating just re-reads the
 *  now-current version. */
export function useFinancialConfig() {
  return useQuery({ queryKey: ["financial-config"], queryFn: api.getFinancialConfig });
}

export function useSetFinancialConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: api.FinancialAssumptionsInput) => api.setFinancialConfig(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["financial-config"] }),
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

export function useAdminVendorUsers(vendorId: string) {
  return useQuery({
    queryKey: ["admin-vendor-users", vendorId],
    queryFn: () => api.listVendorUsers(vendorId),
  });
}

export function useCreateAdminVendorUser(vendorId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: api.NewVendorUserInput) => api.createVendorUser(vendorId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-vendor-users", vendorId] }),
  });
}

export function useSetAdminVendorUserStatus(vendorId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: "active" | "inactive" }) =>
      api.setVendorUserStatus(vendorId, userId, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-vendor-users", vendorId] }),
  });
}

// -----------------------------------------------------------------------------
// Notifications
// -----------------------------------------------------------------------------

export function useNotifications() {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.listNotifications(),
    refetchInterval: 30000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.markNotificationRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
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

export function useCheck(checkId: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["check", checkId],
    queryFn: () => api.getCheck(checkId),
    enabled: (options.enabled ?? true) && checkId !== "",
  });
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

/** The 3D rooftop viewer's geometry (build_scene_geometry()'s roof/walls/
 *  panels/mounting/obstacle meshes). Its own query, same reasoning as
 *  useCheckSolarLayout: a slow/failed 3D fetch must never hold up the rest
 *  of the result page. Only mounted (and so only fetched) once the "View
 *  roof in 3D" panel is actually opened — see Scene3DSection.tsx. */
export function useCheckScene(checkId: string) {
  return useQuery({
    queryKey: ["check", checkId, "scene"],
    queryFn: () => api.getCheckScene(checkId),
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

/** The customer marking something that's really on their roof. Writes
 *  into the same typed obstacle store the AI pipeline uses, so the
 *  obstacles query is the only thing to invalidate — the merged list
 *  refreshes itself. The site is invalidated too because the write
 *  versions the geometry (exclusions). */
export function useMarkCheckObstacle(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { type: api.ObstacleType; lat: number; lng: number }) =>
      api.markCheckObstacle(checkId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check", checkId, "obstacles"] });
      qc.invalidateQueries({ queryKey: ["check", checkId] });
    },
  });
}

/** Removing one the customer placed themselves. An AI detection is
 *  reversed through the audited admin path, and the server 403s here. */
export function useUnmarkCheckObstacle(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (obstacleId: string) => api.unmarkCheckObstacle(checkId, obstacleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check", checkId, "obstacles"] });
      qc.invalidateQueries({ queryKey: ["check", checkId] });
    },
  });
}

/** FIN-02 — the year-by-year ROI projection, its own query since it's a
 *  separate backend call from useCheck() (never part of the Assessment
 *  payload — see getCheckFinancialProjection()'s own docstring). Keyed
 *  on `params` so toggling the financing comparison or exploring a
 *  different down-payment/rate/tenure re-fetches under its own cache
 *  entry rather than fighting the default view for one slot. */
export function useCheckFinancialProjection(checkId: string, params: api.FinancialProjectionParams = {}) {
  return useQuery({
    queryKey: ["check", checkId, "financial-projection", params],
    queryFn: () => api.getCheckFinancialProjection(checkId, params),
    staleTime: 60 * 60 * 1000,
    retry: 1,
  });
}

/** Nearby/available vendors for a check's enquiry step — real district/
 *  state matching, customer-safe fields only (see api.NearbyVendor). */
export function useNearbyVendors(checkId: string) {
  return useQuery({
    queryKey: ["check", checkId, "vendors"],
    queryFn: () => api.listNearbyVendors(checkId),
  });
}

/** The customer's own act of turning a viewed result into an enquiry —
 *  idempotent server-side, but still invalidates the check so the
 *  result page's reviewStatus/enquirySubmittedAt reflect it immediately. */
export function useRaiseEnquiry(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { vendorId?: string } = {}) => api.raiseEnquiry(checkId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check", checkId] });
      qc.invalidateQueries({ queryKey: ["checks"] });
    },
  });
}

export function useCreateCheck() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: NewCheckInput) => api.createCheck(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["checks"] }),
  });
}

/** StartCheckWizard's click-to-locate step. A mutation, not a cached
 *  query — it's fired once per user click, not something to re-fetch or
 *  keep warm in the background. */
export function useResolveBuildingAt() {
  return useMutation({
    mutationFn: ({ lat, lng }: { lat: number; lng: number }) => api.resolveBuildingAt(lat, lng),
  });
}

/** Same endpoint as useResolveBuildingAt above, as a cached query instead
 *  of a mutation — for StartCheckWizard's Locate step, where the lookup
 *  (principally for the real roof-pitch-at-the-pin data in the response)
 *  should re-run automatically whenever the pin moves, not only on an
 *  explicit button click. Rounds to ~11cm so a sub-pixel drag jitter
 *  doesn't refire the same billed Solar API call twice. */
export function useRoofPitchAtPoint(point: { lat: number; lng: number } | null) {
  const rounded = point ? { lat: Number(point.lat.toFixed(6)), lng: Number(point.lng.toFixed(6)) } : null;
  return useQuery({
    queryKey: ["resolve-building-pitch", rounded],
    queryFn: () => api.resolveBuildingAt(rounded!.lat, rounded!.lng),
    enabled: rounded != null,
    staleTime: 5 * 60 * 1000,
  });
}

export function useCompleteCheck(checkId: string) {
  // Only starts the background assessment job now — see
  // useCheckAssessmentStatus below for the poll that finds out when (and
  // at what stage) it actually finishes. No cache invalidation here: the
  // check itself hasn't changed yet, only a job has been dispatched.
  return useMutation({
    mutationFn: () => api.completeCheck(checkId),
  });
}

const TERMINAL_ASSESSMENT_STATUSES = new Set(["ok", "not_found", "geometry_rejected", "error"]);

export function useCheckAssessmentStatus(checkId: string, jobId: string | null) {
  return useQuery({
    queryKey: ["check-assessment-status", checkId, jobId],
    queryFn: () => api.getCheckAssessmentStatus(checkId, jobId as string),
    enabled: jobId != null,
    // Stops polling once the job reaches a terminal status — "pending"/
    // "progress" are the only states worth checking again.
    refetchInterval: (query) => {
      const jobStatus = query.state.data?.status;
      return jobStatus && TERMINAL_ASSESSMENT_STATUSES.has(jobStatus) ? false : 1200;
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

// -----------------------------------------------------------------------------
// Installation projects
//
// Key convention follows the rest of this file: singular + id for one
// item, plural for a list. The QC/commissioning/photo children are keyed
// under their project id so a mutation invalidates exactly the screens
// showing that project, plus the list its status appears in.
// -----------------------------------------------------------------------------

export function useAcceptQuotation(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.acceptQuotation(checkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check-installation", checkId] });
      qc.invalidateQueries({ queryKey: ["check", checkId] });
      qc.invalidateQueries({ queryKey: ["checks"] });
    },
  });
}

export function useCheckInstallation(checkId: string, enabled = true) {
  return useQuery({
    queryKey: ["check-installation", checkId],
    queryFn: () => api.getCheckInstallation(checkId),
    enabled,
    // A 404 here means "no project yet", a normal state for most checks —
    // retrying it would just burn requests on every result page view.
    retry: false,
  });
}

export function useAcceptInstallation(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.acceptInstallation(checkId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["check-installation", checkId] }),
  });
}

/** Only callable once the customer has accepted the finished
 *  installation (server-enforced — see app_checks.py::submit_vendor_review).
 *  Invalidates the vendor list too, since a fresh review changes that
 *  vendor's averageRating/reviewCount everywhere it's shown. */
export function useSubmitVendorReview(checkId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { rating: number; comment?: string }) => api.submitVendorReview(checkId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["check", checkId, "vendors"] });
      qc.invalidateQueries({ queryKey: ["vendor-reviews"] });
    },
  });
}

export function useVendorReviews(checkId: string, vendorId: string | undefined, enabled = true) {
  return useQuery({
    queryKey: ["vendor-reviews", checkId, vendorId],
    queryFn: () => api.listVendorReviews(checkId, vendorId as string),
    enabled: enabled && !!vendorId,
  });
}

// --- vendor -----------------------------------------------------------------

export function useVendorInstallations(params: { status?: string } = {}) {
  return useQuery({
    queryKey: ["vendor-installations", params],
    queryFn: () => api.listVendorInstallations(params),
  });
}

export function useVendorInstallation(projectId: string) {
  return useQuery({
    queryKey: ["vendor-installation", projectId],
    queryFn: () => api.getVendorInstallation(projectId),
  });
}

export function useAdvanceInstallationStatus(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { status: string; panelModel?: string; inverterModel?: string }) =>
      api.advanceVendorInstallationStatus(projectId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["vendor-installation", projectId] });
      qc.invalidateQueries({ queryKey: ["vendor-installations"] });
    },
  });
}

export function useVendorInstallationQc(projectId: string) {
  return useQuery({
    queryKey: ["installation-qc", projectId],
    queryFn: () => api.getVendorInstallationQc(projectId),
  });
}

export function useSaveInstallationQc(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { checklist: InstallationQcItems; notes?: string | null }) =>
      api.saveVendorInstallationQc(projectId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["installation-qc", projectId] }),
  });
}

export function useSubmitInstallationQc(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { checklist: InstallationQcItems; notes?: string | null }) =>
      api.submitVendorInstallationQc(projectId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["installation-qc", projectId] });
      qc.invalidateQueries({ queryKey: ["vendor-installation", projectId] });
    },
  });
}

export function useInstallationPhotos(projectId: string, params: { stage?: string } = {}) {
  return useQuery({
    queryKey: ["installation-photos", projectId, params],
    queryFn: () => api.listVendorInstallationPhotos(projectId, params),
  });
}

export function useAddInstallationPhoto(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { stage: string; dataUrl: string; lat?: number | null; lng?: number | null }) =>
      api.addVendorInstallationPhoto(projectId, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["installation-photos", projectId] }),
  });
}

export function useVendorCommissioning(projectId: string) {
  return useQuery({
    queryKey: ["installation-commissioning", projectId],
    queryFn: () => api.getVendorCommissioning(projectId),
    // 404 until the vendor submits one — a normal state, not an error.
    retry: false,
  });
}

export function useSubmitCommissioning(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CommissioningInput) => api.submitVendorCommissioning(projectId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["installation-commissioning", projectId] });
      qc.invalidateQueries({ queryKey: ["vendor-installation", projectId] });
    },
  });
}

// --- admin ------------------------------------------------------------------

export function useAdminInstallations(params: { status?: string } = {}) {
  return useQuery({
    queryKey: ["admin-installations", params],
    queryFn: () => api.listAdminInstallations(params),
  });
}

export function useAdminInstallation(projectId: string) {
  return useQuery({
    queryKey: ["admin-installation", projectId],
    queryFn: () => api.getAdminInstallation(projectId),
  });
}

export function useSetAdminInstallationStatus(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { status: string; panelModel?: string; inverterModel?: string }) =>
      api.setAdminInstallationStatus(projectId, input),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-installation", projectId] });
      qc.invalidateQueries({ queryKey: ["admin-installations"] });
    },
  });
}

export function useAdminInstallationQc(projectId: string) {
  return useQuery({
    queryKey: ["admin-installation-qc", projectId],
    queryFn: () => api.getAdminInstallationQc(projectId),
  });
}

export function useApproveInstallationQc(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.approveInstallationQc(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-installation-qc", projectId] });
      qc.invalidateQueries({ queryKey: ["admin-installation", projectId] });
    },
  });
}

export function useAdminInstallationPhotos(projectId: string, params: { stage?: string } = {}) {
  return useQuery({
    queryKey: ["admin-installation-photos", projectId, params],
    queryFn: () => api.listAdminInstallationPhotos(projectId, params),
  });
}

export function useAdminCommissioning(projectId: string) {
  return useQuery({
    queryKey: ["admin-installation-commissioning", projectId],
    queryFn: () => api.getAdminCommissioning(projectId),
    retry: false,
  });
}

export function useSaveAdminCommissioning(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CommissioningInput) => api.saveAdminCommissioning(projectId, input),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-installation-commissioning", projectId] }),
  });
}

export function useApproveCommissioning(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.approveCommissioning(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-installation-commissioning", projectId] });
      qc.invalidateQueries({ queryKey: ["admin-installation", projectId] });
      qc.invalidateQueries({ queryKey: ["admin-installations"] });
    },
  });
}
