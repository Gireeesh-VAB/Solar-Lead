"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, ClipboardList, IndianRupee, TrendingUp } from "lucide-react";
import { useVendorEarningsSummary, useVendorJobs, useVendorProfile } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { JobCard } from "@/components/vendor/JobCard";

export function VendorDashboardClient() {
  const jobs = useVendorJobs();
  const earnings = useVendorEarningsSummary();
  const profile = useVendorProfile();

  const items = jobs.data ?? [];
  const queueCount = items.filter((j) => j.status === "queued" || j.status === "accepted").length;
  const atRiskCount = items.filter((j) => j.status === "sla_at_risk" || j.status === "overdue").length;
  const nextJob =
    items.find((j) => j.status === "accepted") ??
    items.find((j) => j.status === "sla_at_risk") ??
    items.find((j) => j.status === "queued");

  return (
    <div className="space-y-8">
      <section aria-labelledby="dashboard-summary-heading">
        <h2 id="dashboard-summary-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Today
        </h2>
        {(jobs.isLoading || earnings.isLoading || profile.isLoading) && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        )}
        {(jobs.isError || earnings.isError) && (
          <ErrorState
            description="Could not load dashboard data."
            onRetry={() => {
              jobs.refetch();
              earnings.refetch();
            }}
          />
        )}
        {jobs.data && earnings.data && profile.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card className="p-4">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <ClipboardList size={13} strokeWidth={1.75} aria-hidden="true" />
                Queue
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">{queueCount}</p>
            </Card>
            <Card className="p-4">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <AlertTriangle size={13} strokeWidth={1.75} aria-hidden="true" />
                SLA at risk
              </p>
              <p className="mt-1 font-mono tabular text-2xl" style={{ color: atRiskCount > 0 ? "var(--bad)" : "var(--ink)" }}>
                {atRiskCount}
              </p>
            </Card>
            <Card className="p-4">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <IndianRupee size={13} strokeWidth={1.75} aria-hidden="true" />
                This week&apos;s earnings
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-ink">₹{earnings.data.weekTotalInr.toLocaleString("en-IN")}</p>
            </Card>
            <Card className="p-4">
              <p className="flex items-center gap-1.5 text-xs text-ink-soft">
                <TrendingUp size={13} strokeWidth={1.75} aria-hidden="true" />
                Accuracy score
              </p>
              <p className="mt-1 font-mono tabular text-2xl text-teal">{profile.data.accuracyScore}%</p>
            </Card>
          </div>
        )}
      </section>

      <section aria-labelledby="next-job-heading">
        <h2 id="next-job-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Next job
        </h2>
        {jobs.isLoading && <CardSkeleton />}
        {jobs.data && nextJob && (
          <div className="space-y-3">
            <JobCard job={nextJob} />
            <Link href={`/vendor/jobs/${nextJob.id}/capture`}>
              <Button>
                Start next job <ArrowRight size={15} strokeWidth={1.75} />
              </Button>
            </Link>
          </div>
        )}
        {jobs.data && !nextJob && (
          <Card className="p-4 text-sm text-ink-soft">No jobs waiting on you right now — check back later.</Card>
        )}
      </section>
    </div>
  );
}
