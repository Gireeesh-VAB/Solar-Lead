"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  useAdminAssessment,
  useApproveAssessment,
  useReassignAssessment,
  useRejectAssessment,
  useAdminVendors,
  useCheck,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ResultPageContent } from "@/app/(customer)/check/[checkId]/result/ResultPageContent";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { formatDate, formatDateTime, formatKwp } from "@/lib/utils";
import { CheckCircle2, XCircle, ShieldCheck, Clock, ExternalLink, ClipboardList } from "lucide-react";
import type { ReviewStatus } from "@/lib/api/client";

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  not_submitted: "Not yet submitted by customer",
  pending: "Pending admin review",
  approved: "Approved — vendor assigned",
  rejected: "Rejected",
  not_applicable: "Not applicable",
};

export function AssessmentReviewClient({ assessmentId }: { assessmentId: string }) {
  const assessment = useAdminAssessment(assessmentId);
  const approve = useApproveAssessment(assessmentId);
  const reassign = useReassignAssessment(assessmentId);
  const reject = useRejectAssessment(assessmentId);
  const vendors = useAdminVendors({ verificationStatus: "verified" });
  // The exact same data GET /check/{id}/result itself fetches — reused
  // here so the result page shows immediately on the review page, not
  // behind an extra click. Only admin-readable via routers/app_checks.py
  // ::_readable_check_or_404().
  const check = useCheck(assessment.data?.siteId ?? "", { enabled: !!assessment.data?.siteId });

  const [vendorId, setVendorId] = useState("");
  const [deadlineDays, setDeadlineDays] = useState(3);
  const [payoutInr, setPayoutInr] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);
  const [showReassign, setShowReassign] = useState(false);
  const [reassignVendorId, setReassignVendorId] = useState("");
  const [reassignReason, setReassignReason] = useState("");

  // Prefill from the customer's own pick — admin can still freely change
  // it before approving. Runs once, the first time it becomes available;
  // a manual change afterward must never be silently overwritten.
  useEffect(() => {
    const pick = assessment.data?.customerSelectedVendorId;
    if (pick && !vendorId) setVendorId(pick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assessment.data?.customerSelectedVendorId]);

  if (assessment.isLoading) return <CardSkeleton className="h-96" />;
  if (assessment.isError || !assessment.data) {
    return <ErrorState description="Could not load this assessment." onRetry={() => assessment.refetch()} />;
  }

  const a = assessment.data;
  const isPending = a.reviewStatus === "pending";
  const vendorName = (id: string | null) => (vendors.data ?? []).find((v) => v.id === id)?.name ?? id;

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card className="p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-ink">{a.siteName}</h2>
              <p className="text-sm text-ink-soft">
                {a.address ? `${a.address} · ` : ""}
                {a.district}
                {a.district && a.state ? ", " : ""}
                {a.state}
              </p>
              <p className="font-mono tabular text-xs text-ink-faint">{a.siteId}</p>
            </div>
            <VerdictChip verdict={a.assessment.verdict} size="lg" />
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-line pt-3 text-sm sm:grid-cols-4">
            <div>
              <p className="text-xs text-ink-faint">Recommended capacity</p>
              <p className="font-mono tabular text-ink">
                {a.assessment.capacityKwp > 0 ? formatKwp(a.assessment.capacityKwp) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Confidence</p>
              <ConfidenceMeter tier={a.assessment.confidence} />
            </div>
            <div>
              <p className="text-xs text-ink-faint">Binding constraint</p>
              <p className="text-ink">{a.assessment.bindingConstraint?.name ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Assessed</p>
              <p className="font-mono tabular text-ink">{formatDate(a.assessment.assessedAt)}</p>
            </div>
          </div>
          <div className="border-t border-line pt-3">
            <Link href={`/admin/assessments/${assessmentId}/feasibility`}>
              <Button variant="secondary" size="sm">
                <ClipboardList size={14} strokeWidth={1.75} />
                Feasibility
              </Button>
            </Link>
          </div>
        </Card>

        {/* The exact same result page the customer sees, shown right away
            on the review page — routers/app_checks.py::
            _readable_check_or_404() is what makes an admin able to load
            this data at all. */}
        {check.isLoading && <CardSkeleton className="h-96" />}
        {check.isError && (
          <ErrorState description="Could not load the full result page." onRetry={() => check.refetch()} />
        )}
        {check.data && !check.data.latestAssessment && (
          <Card className="p-4">
            <p className="text-sm text-ink-soft">No result has been computed for this check yet.</p>
          </Card>
        )}
        {check.data?.latestAssessment && (
          <ResultPageContent assessment={check.data.latestAssessment} check={check.data} defaultSectionsOpen />
        )}
      </div>

      <div className="space-y-4">
        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Review status</h2>
          <div className="flex items-center gap-2">
            {a.reviewStatus === "approved" && <ShieldCheck size={16} className="text-good" strokeWidth={1.75} />}
            {a.reviewStatus === "rejected" && <XCircle size={16} className="text-bad" strokeWidth={1.75} />}
            {a.reviewStatus === "pending" && <Clock size={16} className="text-amber" strokeWidth={1.75} />}
            <p className="text-sm font-medium text-ink">{REVIEW_STATUS_LABEL[a.reviewStatus]}</p>
          </div>
          {a.reviewedBy && a.reviewedAt && (
            <p className="text-xs text-ink-faint">
              Assigned by {a.reviewedBy} · {formatDateTime(a.reviewedAt)}
            </p>
          )}
          {a.enquirySubmittedAt && (
            <p className="text-xs text-ink-faint">
              Enquiry raised {formatDateTime(a.enquirySubmittedAt)}
              {a.customerSelectedVendorId && ` — customer requested ${vendorName(a.customerSelectedVendorId)}`}
            </p>
          )}
          {a.reviewStatus === "rejected" && a.rejectionReason && (
            <p className="rounded-[var(--radius-app)] bg-surface-2 p-2 text-sm text-ink-soft">{a.rejectionReason}</p>
          )}
          {a.reviewStatus === "approved" && a.vendorJobId && (
            <Link
              href={`/admin/vendors/${a.assignedVendorId}`}
              className="inline-flex items-center gap-1 text-sm font-medium text-blue hover:underline"
            >
              View assigned vendor <ExternalLink size={14} strokeWidth={1.75} />
            </Link>
          )}
        </Card>

        {isPending && !showReject && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Approve &amp; assign vendor</h2>
            {a.customerSelectedVendorId ? (
              <p className="text-xs text-ink-soft">
                Customer requested: <span className="font-medium text-ink">{vendorName(a.customerSelectedVendorId)}</span>
                . You can change this before approving.
              </p>
            ) : (
              a.suggestedVendorId && (
                <p className="text-xs text-ink-faint">
                  Suggested by district match: {vendorName(a.suggestedVendorId)}
                </p>
              )
            )}
            <div>
              <label htmlFor="vendor-select" className="mb-1 block text-xs text-ink-faint">
                Vendor
              </label>
              <select
                id="vendor-select"
                value={vendorId}
                onChange={(e) => setVendorId(e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              >
                <option value="">Select a verified vendor…</option>
                {(vendors.data ?? []).map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} · {v.serviceArea}
                  </option>
                ))}
              </select>
              {vendors.data && vendors.data.length === 0 && (
                <p className="mt-1 text-xs text-ink-faint">No verified vendors yet — verify one first.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="deadline-days" className="mb-1 block text-xs text-ink-faint">
                  Survey deadline (days)
                </label>
                <input
                  id="deadline-days"
                  type="number"
                  min={1}
                  max={30}
                  value={deadlineDays}
                  onChange={(e) => setDeadlineDays(Number(e.target.value))}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
                />
              </div>
              <div>
                <label htmlFor="payout-inr" className="mb-1 block text-xs text-ink-faint">
                  Payout ₹ (optional)
                </label>
                <input
                  id="payout-inr"
                  type="number"
                  min={0}
                  placeholder="Auto"
                  value={payoutInr}
                  onChange={(e) => setPayoutInr(e.target.value)}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
                />
              </div>
            </div>
            {approve.isError && <p className="text-xs text-bad">{(approve.error as Error).message}</p>}
            <div className="flex gap-2">
              <Button
                className="flex-1"
                disabled={!vendorId || approve.isPending}
                onClick={() =>
                  approve.mutate({
                    vendorId,
                    deadlineDays,
                    payoutInr: payoutInr ? Number(payoutInr) : undefined,
                  })
                }
              >
                <CheckCircle2 size={14} strokeWidth={1.75} />
                {approve.isPending ? "Approving…" : "Approve & assign"}
              </Button>
              <Button variant="secondary" onClick={() => setShowReject(true)}>
                Reject
              </Button>
            </div>
          </Card>
        )}

        {isPending && showReject && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Reject this assessment</h2>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason the admin team is rejecting this site…"
              rows={4}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            {reject.isError && <p className="text-xs text-bad">{(reject.error as Error).message}</p>}
            <div className="flex gap-2">
              <Button
                variant="danger"
                className="flex-1"
                disabled={!rejectReason.trim() || reject.isPending}
                onClick={() => reject.mutate(rejectReason.trim())}
              >
                <XCircle size={14} strokeWidth={1.75} />
                {reject.isPending ? "Rejecting…" : "Confirm reject"}
              </Button>
              <Button variant="secondary" onClick={() => setShowReject(false)}>
                Back
              </Button>
            </div>
          </Card>
        )}

        {a.reviewStatus === "approved" && !showReassign && (
          <Card className="p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Vendor assignment</h2>
            <p className="text-sm text-ink-soft">
              Currently assigned to <span className="font-medium text-ink">{vendorName(a.assignedVendorId)}</span>.
            </p>
            <Button variant="secondary" size="sm" onClick={() => setShowReassign(true)}>
              Reassign vendor
            </Button>
          </Card>
        )}

        {a.reviewStatus === "approved" && showReassign && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Reassign vendor</h2>
            <p className="text-xs text-ink-faint">
              Moves the same survey job to a new vendor — the current vendor is recorded in the job's history,
              not removed.
            </p>
            <div>
              <label htmlFor="reassign-vendor-select" className="mb-1 block text-xs text-ink-faint">
                New vendor
              </label>
              <select
                id="reassign-vendor-select"
                value={reassignVendorId}
                onChange={(e) => setReassignVendorId(e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              >
                <option value="">Select a verified vendor…</option>
                {(vendors.data ?? [])
                  .filter((v) => v.id !== a.assignedVendorId)
                  .map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name} · {v.serviceArea}
                    </option>
                  ))}
              </select>
            </div>
            <div>
              <label htmlFor="reassign-reason" className="mb-1 block text-xs text-ink-faint">
                Reason (optional)
              </label>
              <textarea
                id="reassign-reason"
                value={reassignReason}
                onChange={(e) => setReassignReason(e.target.value)}
                placeholder="Why is this job moving to a new vendor…"
                rows={3}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              />
            </div>
            {reassign.isError && <p className="text-xs text-bad">{(reassign.error as Error).message}</p>}
            <div className="flex gap-2">
              <Button
                className="flex-1"
                disabled={!reassignVendorId || reassign.isPending}
                onClick={() =>
                  reassign.mutate(
                    { vendorId: reassignVendorId, reason: reassignReason.trim() || undefined },
                    { onSuccess: () => { setShowReassign(false); setReassignReason(""); } }
                  )
                }
              >
                {reassign.isPending ? "Reassigning…" : "Confirm reassign"}
              </Button>
              <Button variant="secondary" onClick={() => setShowReassign(false)}>
                Cancel
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
