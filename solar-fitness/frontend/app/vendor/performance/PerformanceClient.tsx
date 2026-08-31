"use client";

import { TrendingDown, TrendingUp } from "lucide-react";
import { useVendorProfile, useVendorSubmissions } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Badge } from "@/components/ui/Primitives";

const BANDS = [
  { label: "Within 5%", test: (v: number) => Math.abs(v) <= 5, tone: "blue" as const },
  { label: "5–10%", test: (v: number) => Math.abs(v) > 5 && Math.abs(v) <= 10, tone: "amber" as const },
  { label: "Over 10%", test: (v: number) => Math.abs(v) > 10, tone: "amber" as const },
];

export function PerformanceClient() {
  const profile = useVendorProfile();
  const submissions = useVendorSubmissions();

  const trend = profile.data?.accuracyTrend ?? [];
  const latest = trend.at(-1)?.score ?? 0;
  const prior = trend.at(-2)?.score ?? latest;
  const trendUp = latest >= prior;

  return (
    <div className="space-y-8">
      <section aria-labelledby="accuracy-heading">
        <h2 id="accuracy-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Accuracy score
        </h2>
        {profile.isLoading && <CardSkeleton />}
        {profile.isError && <ErrorState description="Could not load performance data." onRetry={() => profile.refetch()} />}
        {profile.data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Card className="p-4">
              <p className="text-xs text-ink-soft">Current score</p>
              <p className="mt-1 flex items-center gap-2 font-mono tabular text-3xl text-ink">
                {latest}%
                {trendUp ? (
                  <TrendingUp size={20} strokeWidth={1.75} style={{ color: "var(--good)" }} aria-hidden="true" />
                ) : (
                  <TrendingDown size={20} strokeWidth={1.75} style={{ color: "var(--bad)" }} aria-hidden="true" />
                )}
              </p>
              <p className="mt-1 text-xs text-ink-soft">{trendUp ? "Trending up" : "Trending down"} vs. last period</p>
            </Card>
            <Card className="p-4">
              <p className="mb-2 text-xs text-ink-soft">Recent trend</p>
              <div className="flex flex-wrap gap-1.5">
                {trend.map((p) => (
                  <Badge key={p.label} tone="blue">
                    {p.label}: {p.score}%
                  </Badge>
                ))}
              </div>
            </Card>
          </div>
        )}
      </section>

      <section aria-labelledby="variance-heading">
        <h2 id="variance-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Jobs by variance band
        </h2>
        {submissions.isLoading && <CardSkeleton />}
        {submissions.isError && <ErrorState description="Could not load submissions." onRetry={() => submissions.refetch()} />}
        {submissions.data && (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {BANDS.map((band) => {
              const count = submissions.data.filter((j) => band.test(j.variancePct ?? 0)).length;
              return (
                <Card key={band.label} className="p-4">
                  <p className="text-xs text-ink-soft">{band.label}</p>
                  <p className="mt-1 font-mono tabular text-2xl text-ink">{count}</p>
                </Card>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
