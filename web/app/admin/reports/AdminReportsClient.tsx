"use client";

import { useState } from "react";
import { useAllAssessments, useTenants } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { Download } from "lucide-react";

const TIER_MRR_INR: Record<string, number> = { starter: 4999, growth: 19999, enterprise: 79999 };
const CACHE_SAVING_PER_HIT_INR = 6;

export function AdminReportsClient() {
  const tenants = useTenants();
  const assessments = useAllAssessments({ pageSize: 5000 });
  const [exportMsg, setExportMsg] = useState<string | null>(null);

  if (tenants.isLoading || assessments.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  if (tenants.isError || assessments.isError || !tenants.data || !assessments.data) {
    return (
      <ErrorState
        description="Could not load report data."
        onRetry={() => {
          tenants.refetch();
          assessments.refetch();
        }}
      />
    );
  }

  const activeTenants = tenants.data.filter((t) => t.status === "active");
  const mrrInr = activeTenants.reduce((sum, t) => sum + (TIER_MRR_INR[t.tier] ?? 0), 0);
  const cacheHits = assessments.data.items.filter((row) => row.assessment.cache.cacheHit).length;
  const cacheSavingsInr = cacheHits * CACHE_SAVING_PER_HIT_INR;
  const totalApiCalls = tenants.data.reduce((sum, t) => sum + t.apiCallsThisMonth, 0);

  const byTier = ["starter", "growth", "enterprise"].map((tier) => {
    const tierTenants = tenants.data!.filter((t) => t.tier === tier);
    return {
      tier,
      count: tierTenants.length,
      mrr: tierTenants.filter((t) => t.status === "active").reduce((sum, t) => sum + (TIER_MRR_INR[tier] ?? 0), 0),
      sites: tierTenants.reduce((sum, t) => sum + t.sitesAssessedThisMonth, 0),
    };
  });

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Est. monthly revenue</p>
          <p className="mt-1 font-mono tabular text-2xl text-slate">₹{mrrInr.toLocaleString("en-IN")}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Assessment cache savings</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">₹{cacheSavingsInr.toLocaleString("en-IN")}</p>
          <p className="mt-1 text-xs text-ink-faint">{cacheHits} cache-hit assessments</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Total API calls (30d)</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{totalApiCalls.toLocaleString("en-IN")}</p>
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Breakdown by tier</h2>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setExportMsg("Export queued — you'll receive a download link by email shortly.")}
          >
            <Download size={14} strokeWidth={1.75} /> Export
          </Button>
        </div>
        {exportMsg && <p className="mt-2 text-xs text-ink-soft">{exportMsg}</p>}
        <div className="mt-3 overflow-x-auto scrollbar-thin">
          <table className="w-full min-w-[500px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
                <th scope="col" className="py-2 pr-3 font-medium">Tier</th>
                <th scope="col" className="py-2 pr-3 font-medium text-right">Tenants</th>
                <th scope="col" className="py-2 pr-3 font-medium text-right">MRR</th>
                <th scope="col" className="py-2 pr-3 font-medium text-right">Sites this month</th>
              </tr>
            </thead>
            <tbody>
              {byTier.map((row, i) => (
                <tr key={row.tier} className={i % 2 === 1 ? "bg-surface" : undefined}>
                  <td className="py-2.5 pr-3 capitalize text-ink">{row.tier}</td>
                  <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{row.count}</td>
                  <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">₹{row.mrr.toLocaleString("en-IN")}</td>
                  <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{row.sites.toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
