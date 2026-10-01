"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, ShieldCheck, Sigma } from "lucide-react";
import {
  useAdminVendors,
  useCalibrationProposals,
  useModelVersions,
  usePlatformHealth,
  useVendorVerificationQueue,
} from "@/lib/query/hooks";
import { Badge, Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { QuotaBar } from "@/components/admin/QuotaBar";
import { MiniBarChart } from "@/components/admin/MiniBarChart";

export function AdminDashboardClient() {
  const health = usePlatformHealth();
  const vendors = useAdminVendors();
  const verificationQueue = useVendorVerificationQueue();
  const calibration = useCalibrationProposals();
  const models = useModelVersions();

  const loading = health.isLoading || vendors.isLoading || verificationQueue.isLoading || calibration.isLoading || models.isLoading;
  const errored = health.isError || vendors.isError || verificationQueue.isError || calibration.isError || models.isError;

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (errored || !health.data || !vendors.data || !verificationQueue.data || !calibration.data || !models.data) {
    return (
      <ErrorState
        description="Could not load dashboard data."
        onRetry={() => {
          health.refetch();
          vendors.refetch();
          verificationQueue.refetch();
          calibration.refetch();
          models.refetch();
        }}
      />
    );
  }

  const atRiskVendors = vendors.data.filter((v) => v.verificationStatus === "suspended" || v.slaCompliancePct > 0 && v.slaCompliancePct < 80);
  const pendingCalibration = calibration.data.filter((c) => c.status === "pending_approval");
  const pendingModels = models.data.filter((m) => m.status === "proposed");
  const warningQuotas = health.data.quotas.filter((q) => q.used / q.limit >= 0.85);
  // Purely a second reading of the vendor list already fetched above — no
  // extra request, no derived numbers that aren't already on this page.
  const countByStatus = (status: string) => vendors.data!.filter((v) => v.verificationStatus === status).length;
  const vendorStatusBreakdown = [
    { label: "Verified", value: countByStatus("verified"), color: "var(--good)" },
    { label: "Pending", value: countByStatus("pending"), color: "var(--warn)" },
    { label: "Rejected", value: countByStatus("rejected"), color: "var(--bad)" },
    { label: "Suspended", value: countByStatus("suspended"), color: "var(--neutral-verdict)" },
  ];

  return (
    <div className="space-y-8">
      <section aria-labelledby="platform-health-heading">
        <h2 id="platform-health-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Platform health
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_2fr]">
          <Link href="/admin/configuration">
            <Card interactive className="p-4 h-full">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <ShieldCheck size={13} strokeWidth={1.75} aria-hidden="true" />
                Uptime (30d)
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{health.data.uptimePct}%</p>
              <p className="mt-1 text-xs text-ink-faint">{health.data.incidentsThisMonth} incident(s) this month</p>
            </Card>
          </Link>
          <Card className="p-4 space-y-3">
            {health.data.quotas.map((q) => (
              <QuotaBar key={q.service} quota={q} />
            ))}
          </Card>
        </div>
      </section>

      <section aria-labelledby="exceptions-heading">
        <h2 id="exceptions-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Open exceptions
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Link href="/admin/vendors/verification">
            <Card interactive className="p-4 h-full">
              <p className="text-xs text-ink-soft">Pending verifications</p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{verificationQueue.data.length}</p>
              {verificationQueue.data.length > 0 && (
                <Badge tone="amber" className="mt-1.5">Needs review</Badge>
              )}
            </Card>
          </Link>
          <Link href="/admin/platform/calibration">
            <Card interactive className="p-4 h-full">
              <p className="text-xs text-ink-soft">Pending calibration</p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{pendingCalibration.length}</p>
              {pendingCalibration.length > 0 && (
                <Badge tone="amber" className="mt-1.5">Awaiting approval</Badge>
              )}
            </Card>
          </Link>
          <Link href="/admin/platform/models">
            <Card interactive className="p-4 h-full">
              <p className="text-xs text-ink-soft">Pending model approvals</p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{pendingModels.length}</p>
              {pendingModels.length > 0 && (
                <Badge tone="amber" className="mt-1.5">Awaiting approval</Badge>
              )}
            </Card>
          </Link>
          <Link href="/admin/vendors">
            <Card interactive className="p-4 h-full">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <AlertTriangle size={13} strokeWidth={1.75} aria-hidden="true" />
                Vendors at risk
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{atRiskVendors.length}</p>
              {atRiskVendors.length > 0 && (
                <Badge tone="red" className="mt-1.5">At risk</Badge>
              )}
            </Card>
          </Link>
        </div>
        {warningQuotas.length > 0 && (
          <Link href="/admin/configuration" className="mt-3 flex items-center gap-2 rounded-[var(--radius-app)] border py-2 px-3 text-sm" style={{ borderColor: "var(--bad)", background: "var(--bad-bg)", color: "var(--bad)" }}>
            <AlertTriangle size={14} strokeWidth={1.75} aria-hidden="true" />
            {warningQuotas.length} API quota(s) above 85% usage — review configuration
            <ArrowRight size={14} strokeWidth={1.75} className="ml-auto" aria-hidden="true" />
          </Link>
        )}
      </section>

      <section aria-labelledby="activity-heading">
        <h2 id="activity-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Vendor activity
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[1fr_2fr]">
          <Link href="/admin/vendors">
            <Card interactive className="p-4 h-full">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Sigma size={13} strokeWidth={1.75} aria-hidden="true" />
                Verified vendors
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-brand">{vendors.data.filter((v) => v.verificationStatus === "verified").length}</p>
              <p className="mt-1 text-xs text-ink-faint">of {vendors.data.length} total</p>
            </Card>
          </Link>
          <Card className="p-4">
            <p className="text-xs text-ink-soft">Verification status breakdown</p>
            <div className="mt-3">
              <MiniBarChart title="Vendor verification status breakdown" data={vendorStatusBreakdown} />
            </div>
          </Card>
        </div>
      </section>
    </div>
  );
}
