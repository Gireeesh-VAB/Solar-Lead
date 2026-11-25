"use client";

import { useState } from "react";
import {
  useAdminVendor,
  useAdminVendorJobs,
  useAdminVendorPayouts,
  useAdminVendorStatusAction,
  useAdminVendorUsers,
  useCreateAdminVendorUser,
  useSetAdminVendorUserStatus,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate, formatPercent } from "@/lib/utils";
import { ApiError } from "@/lib/api/fetchClient";
import type { NewVendorUserResult } from "@/lib/api/client";
import { Ban, CheckCircle2, Copy, UserPlus } from "lucide-react";

const inputClass =
  "w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue";

function VendorUsersCard({ vendorId }: { vendorId: string }) {
  const users = useAdminVendorUsers(vendorId);
  const createUser = useCreateAdminVendorUser(vendorId);
  const setStatus = useSetAdminVendorUserStatus(vendorId);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [created, setCreated] = useState<NewVendorUserResult | null>(null);
  const [copied, setCopied] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    try {
      const result = await createUser.mutateAsync({ name, email });
      setCreated(result);
      setCopied(false);
      setName("");
      setEmail("");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    }
  };

  return (
    <Card className="p-4 space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Vendor users</h2>

      {users.isLoading && <p className="text-sm text-ink-soft">Loading…</p>}
      {users.data && users.data.length === 0 && (
        <p className="text-sm text-ink-soft">No additional logins for this vendor yet.</p>
      )}
      {users.data && users.data.length > 0 && (
        <ul className="divide-y divide-line">
          {users.data.map((u) => (
            <li key={u.id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <div>
                <p className="text-ink">{u.name}</p>
                <p className="text-xs text-ink-faint">{u.email}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="capitalize text-xs text-ink-soft">{u.status}</span>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={setStatus.isPending}
                  onClick={() =>
                    setStatus.mutate({ userId: u.id, status: u.status === "active" ? "inactive" : "active" })
                  }
                >
                  {u.status === "active" ? "Deactivate" : "Activate"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {created && (
        <div className="space-y-2 rounded-[var(--radius-app)] border border-line bg-surface p-3">
          <p className="text-sm text-ink-soft">
            Share this login with {created.user.name} now — the temporary password won&apos;t be shown again.
          </p>
          <div>
            <p className="text-xs text-ink-faint">Login email</p>
            <p className="font-mono tabular text-sm text-ink">{created.loginEmail}</p>
          </div>
          <div>
            <p className="text-xs text-ink-faint">Temporary password</p>
            <div className="flex items-center gap-2">
              <p className="font-mono tabular text-sm text-ink">{created.temporaryPassword}</p>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard?.writeText(created.temporaryPassword);
                  setCopied(true);
                }}
                className="inline-flex items-center gap-1 text-xs text-ink-soft hover:text-ink"
              >
                <Copy size={12} strokeWidth={1.75} /> {copied ? "Copied" : "Copy"}
              </button>
            </div>
          </div>
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2 pt-2">
        <div className="flex-1 min-w-[10rem]">
          <label htmlFor="vendor-user-name" className="mb-1 block text-xs text-ink-faint">
            Name
          </label>
          <input
            id="vendor-user-name"
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="flex-1 min-w-[10rem]">
          <label htmlFor="vendor-user-email" className="mb-1 block text-xs text-ink-faint">
            Email
          </label>
          <input
            id="vendor-user-email"
            type="email"
            className={inputClass}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <Button type="submit" size="sm" disabled={createUser.isPending}>
          <UserPlus size={14} strokeWidth={1.75} /> Add user
        </Button>
      </form>
      {formError && (
        <p className="text-xs" style={{ color: "var(--bad)" }}>
          {formError}
        </p>
      )}
    </Card>
  );
}

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
          <p className="mt-1 font-mono tabular text-2xl text-ink">{v.slaCompliancePct ? formatPercent(v.slaCompliancePct) : "—"}</p>
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

      <VendorUsersCard vendorId={vendorId} />

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
