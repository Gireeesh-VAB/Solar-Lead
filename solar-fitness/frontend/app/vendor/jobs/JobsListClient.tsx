"use client";

import { useState } from "react";
import { ClipboardList } from "lucide-react";
import { useVendorJobs } from "@/lib/query/hooks";
import { CardSkeleton, ErrorState, EmptyState } from "@/components/ui/Primitives";
import { Select } from "@/components/ui/Select";
import { JobCard } from "@/components/vendor/JobCard";
import { VENDOR_STATUS_LABEL } from "@/components/vendor/SlaBadge";
import type { VendorJobStatus } from "@/lib/types";

const STATUSES: VendorJobStatus[] = ["queued", "accepted", "in_progress", "sla_at_risk", "overdue", "submitted"];

export function JobsListClient() {
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<"deadline" | "distance" | "payout">("deadline");
  const jobs = useVendorJobs({ status: status || undefined, sort });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Filter by status"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {VENDOR_STATUS_LABEL[s]}
            </option>
          ))}
        </Select>
        <Select
          value={sort}
          onChange={(e) => setSort(e.target.value as typeof sort)}
          aria-label="Sort jobs"
        >
          <option value="deadline">Sort by deadline</option>
          <option value="distance">Sort by distance</option>
          <option value="payout">Sort by payout</option>
        </Select>
      </div>

      {jobs.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}
      {jobs.isError && <ErrorState description="Could not load your job queue." onRetry={() => jobs.refetch()} />}
      {jobs.data && jobs.data.length === 0 && (
        <EmptyState
          icon={<ClipboardList size={28} strokeWidth={1.5} />}
          title="No jobs match these filters"
          description="Try a different status filter, or check back later for new assignments."
        />
      )}
      {jobs.data && jobs.data.length > 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {jobs.data.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </div>
  );
}
