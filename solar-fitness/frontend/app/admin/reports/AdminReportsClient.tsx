"use client";

import { useAllAssessments } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { MiniBarChart } from "@/components/admin/MiniBarChart";

const CACHE_SAVING_PER_HIT_INR = 6;

export function AdminReportsClient() {
  const assessments = useAllAssessments({ pageSize: 5000 });

  if (assessments.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <CardSkeleton />
      </div>
    );
  }
  if (assessments.isError || !assessments.data) {
    return <ErrorState description="Could not load report data." onRetry={() => assessments.refetch()} />;
  }

  const cacheHits = assessments.data.items.filter((row) => row.assessment.cache.cacheHit).length;
  const cacheSavingsInr = cacheHits * CACHE_SAVING_PER_HIT_INR;
  // Same already-fetched assessment list the savings figure is computed
  // from, split two ways — no additional request.
  const freshComputes = assessments.data.items.length - cacheHits;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Assessment cache savings</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">₹{cacheSavingsInr.toLocaleString("en-IN")}</p>
          <p className="mt-1 text-xs text-ink-faint">{cacheHits} cache-hit assessments</p>
        </Card>
        <Card className="p-4 sm:col-span-2">
          <p className="text-xs text-ink-soft">Cache hits vs fresh computes</p>
          <div className="mt-3">
            <MiniBarChart
              title="Assessments served from cache versus freshly computed"
              data={[
                { label: "Cache hits", value: cacheHits, color: "var(--brand)" },
                { label: "Fresh computes", value: freshComputes, color: "var(--slate)" },
              ]}
            />
          </div>
          <p className="mt-2 text-xs text-ink-faint">{assessments.data.items.length} assessments total</p>
        </Card>
      </div>
    </div>
  );
}
