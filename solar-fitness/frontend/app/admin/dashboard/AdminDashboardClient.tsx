"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Building2, IndianRupee, ShieldCheck, Sigma } from "lucide-react";
import {
  useAdminVendors,
  useCalibrationProposals,
  useModelVersions,
  usePlatformHealth,
  useTenants,
  useVendorVerificationQueue,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { QuotaBar } from "@/components/admin/QuotaBar";

const TIER_MRR_INR: Record<string, number> = { starter: 4999, growth: 19999, enterprise: 79999 };

export function AdminDashboardClient() {
  const health = usePlatformHealth();
  const tenants = useTenants();
  const vendors = useAdminVendors();
  const verificationQueue = useVendorVerificationQueue();
  const calibration = useCalibrationProposals();
  const models = useModelVersions();

  const loading = health.isLoading || tenants.isLoading || vendors.isLoading || verificationQueue.isLoading || calibration.isLoading || models.isLoading;
  const errored = health.isError || tenants.isError || vendors.isError || verificationQueue.isError || calibration.isError || models.isError;

  if (loading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (errored || !health.data || !tenants.data || !vendors.data || !verificationQueue.data || !calibration.data || !models.data) {
    return (
      <ErrorState
        description="Could not load dashboard data."
        onRetry={() => {
          health.refetch();
          tenants.refetch();
          vendors.refetch();
          verificationQueue.refetch();
          calibration.refetch();
          models.refetch();
        }}
      />
    );
  }

  const activeTenants = tenants.data.filter((t) => t.status === "active");
  const suspendedTenants = tenants.data.filter((t) => t.status === "suspended");
  const mrrInr = activeTenants.reduce((sum, t) => sum + (TIER_MRR_INR[t.tier] ?? 0), 0);
  const atRiskVendors = vendors.data.filter((v) => v.verificationStatus === "suspended" || v.slaCompliancePct > 0 && v.slaCompliancePct < 80);
  const pendingCalibration = calibration.data.filter((c) => c.status === "pending_approval");
  const pendingModels = models.data.filter((m) => m.status === "proposed");
  const warningQuotas = health.data.quotas.filter((q) => q.used / q.limit >= 0.85);

  return (
    <div className="space-y-8">
      <section aria-labelledby="platform-health-heading">
        <h2 id="platform-health-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Platform health
        </h2>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_2fr]">
          <Link href="/admin/configuration">
            <Card className="p-4 h-full hover:border-slate">
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
            <Card className="p-4 h-full hover:border-slate">
              <p className="text-xs text-ink-soft">Pending verifications</p>
              <p className="mt-1 font-mono tabular text-2xl" style={{ color: verificationQueue.data.length > 0 ? "var(--warn)" : "var(--ink)" }}>
                {verificationQueue.data.length}
              </p>
            </Card>
          </Link>
          <Link href="/admin/platform/calibration">
            <Card className="p-4 h-full hover:border-slate">
              <p className="text-xs text-ink-soft">Pending calibration</p>
              <p className="mt-1 font-mono tabular text-2xl" style={{ color: pendingCalibration.length > 0 ? "var(--warn)" : "var(--ink)" }}>
                {pendingCalibration.length}
              </p>
            </Card>
          </Link>
          <Link href="/admin/platform/models">
            <Card className="p-4 h-full hover:border-slate">
              <p className="text-xs text-ink-soft">Pending model approvals</p>
              <p className="mt-1 font-mono tabular text-2xl" style={{ color: pendingModels.length > 0 ? "var(--warn)" : "var(--ink)" }}>
                {pendingModels.length}
              </p>
            </Card>
          </Link>
          <Link href="/admin/vendors">
            <Card className="p-4 h-full hover:border-slate">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <AlertTriangle size={13} strokeWidth={1.75} aria-hidden="true" />
                Vendors at risk
              </p>
              <p className="mt-1 font-mono tabular text-2xl" style={{ color: atRiskVendors.length > 0 ? "var(--bad)" : "var(--ink)" }}>
                {atRiskVendors.length}
              </p>
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
          Tenant &amp; vendor activity
        </h2>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Link href="/admin/tenants">
            <Card className="p-4 h-full hover:border-slate">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Building2 size={13} strokeWidth={1.75} aria-hidden="true" />
                Active tenants
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{activeTenants.length}</p>
              <p className="mt-1 text-xs text-ink-faint">{suspendedTenants.length} suspended</p>
            </Card>
          </Link>
          <Link href="/admin/vendors">
            <Card className="p-4 h-full hover:border-slate">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <Sigma size={13} strokeWidth={1.75} aria-hidden="true" />
                Verified vendors
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{vendors.data.filter((v) => v.verificationStatus === "verified").length}</p>
              <p className="mt-1 text-xs text-ink-faint">of {vendors.data.length} total</p>
            </Card>
          </Link>
          <Link href="/admin/tenants">
            <Card className="p-4 h-full hover:border-slate">
              <p className="text-xs text-ink-soft">Sites assessed (30d)</p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">
                {tenants.data.reduce((sum, t) => sum + t.sitesAssessedThisMonth, 0).toLocaleString("en-IN")}
              </p>
            </Card>
          </Link>
          <Link href="/admin/reports">
            <Card className="p-4 h-full hover:border-slate">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <IndianRupee size={13} strokeWidth={1.75} aria-hidden="true" />
                Est. monthly revenue
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-slate">₹{mrrInr.toLocaleString("en-IN")}</p>
            </Card>
          </Link>
        </div>
      </section>
    </div>
  );
}
