"use client";

import { useAllAssessments } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";

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

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Assessment cache savings</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">₹{cacheSavingsInr.toLocaleString("en-IN")}</p>
          <p className="mt-1 text-xs text-ink-faint">{cacheHits} cache-hit assessments</p>
        </Card>
      </div>
    </div>
  );
}
