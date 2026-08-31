"use client";

import Link from "next/link";
import { FileCheck2 } from "lucide-react";
import { useVendorSubmissions } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, EmptyState, Badge } from "@/components/ui/Primitives";
import { formatDate } from "@/lib/utils";

export function SubmissionsListClient() {
  const submissions = useVendorSubmissions();

  if (submissions.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    );
  }
  if (submissions.isError) {
    return <ErrorState description="Could not load your submissions." onRetry={() => submissions.refetch()} />;
  }
  if (!submissions.data || submissions.data.length === 0) {
    return (
      <EmptyState
        icon={<FileCheck2 size={28} strokeWidth={1.5} />}
        title="No submissions yet"
        description="Completed jobs you've submitted for reconciliation will show up here."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {submissions.data.map((job) => (
        <Link key={job.id} href={`/vendor/submissions/${job.id}`}>
          <Card className="h-full space-y-2 p-4 hover:border-teal">
            <p className="font-medium text-ink">{job.siteName}</p>
            <p className="text-xs text-ink-soft">
              {job.district}, {job.state}
            </p>
            <p className="text-xs text-ink-faint">Submitted {job.submittedAt ? formatDate(job.submittedAt) : "—"}</p>
            <div className="flex items-center justify-between pt-2">
              <span className="font-mono tabular text-sm text-ink">₹{(job.reconciledPayoutInr ?? job.payoutInr).toLocaleString("en-IN")}</span>
              {job.disputeStatus === "open" && <Badge tone="amber">Dispute open</Badge>}
              {job.disputeStatus === "resolved" && <Badge tone="blue">Dispute resolved</Badge>}
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}
