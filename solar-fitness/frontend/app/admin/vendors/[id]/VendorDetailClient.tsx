"use client";

import { useState } from "react";
import {
  useAdminVendor,
  useAdminVendorJobs,
  useAdminVendorPayouts,
  useAdminVendorStatusAction,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import { Ban, CheckCircle2 } from "lucide-react";

export function VendorDetailClient({ vendorId }: { vendorId: string }) {
  const vendor = useAdminVendor(vendorId);
  const statusAction = useAdminVendorStatusAction(vendorId);
  const jobs = useAdminVendorJobs(vendorId);
  const payouts = useAdminVendorPayouts(vendorId);
  const [confirmOpen, setConfirmOpen] = useState(false);

  if (vendor.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  if (vendor.isError || !vendor.data) {
    return <ErrorState description="Could not load vendor." onRetry={() => vendor.refetch()} />;
  }

  const v = vendor.data;
  const willSuspend = v.verificationStatus !== "suspended";
  const submissions = (jobs.data ?? []).filter((j) => j.status === "submitted").slice(0, 5);
  const totalPaid = (payouts.data ?? []).filter((p) => p.status === "paid").reduce((sum, p) => sum + p.amount, 0);
  const totalPending = (payouts.data ?? []).filter((p) => p.status === "pending").reduce((sum, p) => sum + p.amount, 0);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs text-ink-faint">Accuracy score</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{v.accuracyScore || "—"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-faint">SLA compliance</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{v.slaCompliancePct ? `${v.slaCompliancePct}%` : "—"}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-faint">Jobs completed</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{v.totalJobsCompleted}</p>
        </Card>
      </div>

      <Card className="p-4 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Profile</h2>
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <p className="text-xs text-ink-faint">Verification status</p>
            <p className="capitalize text-ink">{v.verificationStatus}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Service area</p>
            <p className="text-ink">{v.serviceArea}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Active jobs</p>
            <p className="font-mono tabular text-ink">{v.activeJobs}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Joined</p>
            <p className="font-mono tabular text-ink">{formatDate(v.joinedAt)}</p>
          </div>
        </div>
        <div className="pt-2">
          {willSuspend ? (
            <Button variant="danger" size="sm" onClick={() => setConfirmOpen(true)} disabled={statusAction.isPending}>
              <Ban size={14} strokeWidth={1.75} /> Suspend vendor
            </Button>
          ) : (
            <Button variant="secondary" size="sm" onClick={() => setConfirmOpen(true)} disabled={statusAction.isPending}>
              <CheckCircle2 size={14} strokeWidth={1.75} /> Reinstate vendor
            </Button>
          )}
        </div>
      </Card>

      {(v.legalName || v.gstNumber || v.panNumber || v.contactName || v.contactEmail || v.addressLine1 || (v.certifications && v.certifications.length > 0)) && (
        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Business & contact details</h2>
          <div className="grid grid-cols-2 gap-3 text-sm">
            {v.legalName && (
              <div>
                <p className="text-xs text-ink-faint">Legal name</p>
                <p className="text-ink">{v.legalName}</p>
              </div>
            )}
            {v.gstNumber && (
              <div>
                <p className="text-xs text-ink-faint">GST number</p>
                <p className="font-mono tabular text-ink">{v.gstNumber}</p>
              </div>
            )}
            {v.panNumber && (
              <div>
                <p className="text-xs text-ink-faint">PAN number</p>
                <p className="font-mono tabular text-ink">{v.panNumber}</p>
              </div>
            )}
            {v.contactName && (
              <div>
                <p className="text-xs text-ink-faint">Contact person</p>
                <p className="text-ink">{v.contactName}</p>
              </div>
            )}
            {v.contactPhone && (
              <div>
                <p className="text-xs text-ink-faint">Contact phone</p>
                <p className="font-mono tabular text-ink">{v.contactPhone}</p>
              </div>
            )}
            {v.contactEmail && (
              <div>
                <p className="text-xs text-ink-faint">Contact email</p>
                <p className="text-ink">{v.contactEmail}</p>
              </div>
            )}
            {(v.addressLine1 || v.city || v.state || v.pincode) && (
              <div className="col-span-2">
                <p className="text-xs text-ink-faint">Address</p>
                <p className="text-ink">
                  {[v.addressLine1, v.addressLine2, v.city, v.state, v.pincode].filter(Boolean).join(", ")}
                </p>
              </div>
            )}
            {v.certifications && v.certifications.length > 0 && (
              <div className="col-span-2">
                <p className="text-xs text-ink-faint">Certifications</p>
                <p className="text-ink">{v.certifications.join(", ")}</p>
              </div>
            )}
          </div>
        </Card>
      )}

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">Recent submissions</h2>
        {jobs.isLoading && <p className="text-sm text-ink-soft">Loading…</p>}
        {jobs.data && submissions.length === 0 && <p className="text-sm text-ink-soft">No recent submissions.</p>}
        {submissions.length > 0 && (
          <ul className="divide-y divide-line">
            {submissions.map((j) => (
              <li key={j.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                <div>
                  <p className="text-ink">{j.siteName}</p>
                  <p className="text-xs text-ink-faint">{j.district}, {j.state}</p>
                </div>
                <span className="font-mono tabular text-xs text-ink-soft">{j.submittedAt ? formatDate(j.submittedAt) : "—"}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">Payout summary</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-xs text-ink-faint">Total paid</p>
            <p className="font-mono tabular text-xl text-ink">₹{totalPaid.toLocaleString("en-IN")}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Pending payout</p>
            <p className="font-mono tabular text-xl text-ink">₹{totalPending.toLocaleString("en-IN")}</p>
          </div>
        </div>
      </Card>

      <ConfirmDialog
        open={confirmOpen}
        title={willSuspend ? `Suspend ${v.name}?` : `Reinstate ${v.name}?`}
        description={
          willSuspend
            ? "This immediately removes the vendor from the job assignment pool and blocks new job acceptance. This action can be reversed by reinstating the vendor."
            : "This restores the vendor to the active job assignment pool."
        }
        confirmLabel={willSuspend ? "Suspend vendor" : "Reinstate vendor"}
        tone={willSuspend ? "danger" : "primary"}
        pending={statusAction.isPending}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={() =>
          statusAction.mutate(willSuspend ? "suspend" : "reinstate", {
            onSuccess: () => setConfirmOpen(false),
          })
        }
      />
    </div>
  );
}
