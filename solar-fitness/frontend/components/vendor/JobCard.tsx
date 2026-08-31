import Link from "next/link";
import { Clock3, IndianRupee, MapPin } from "lucide-react";
import type { VendorJob } from "@/lib/types";
import { Card } from "@/components/ui/Primitives";
import { SlaBadge } from "@/components/vendor/SlaBadge";
import { siteTypeLabel } from "@/lib/utils";

function deadlineLabel(deadline: string): string {
  const diffMs = new Date(deadline).getTime() - Date.now();
  const diffHours = diffMs / 3_600_000;
  if (diffHours < 0) {
    const overdueDays = Math.ceil(Math.abs(diffHours) / 24);
    return `Overdue by ${overdueDays}d`;
  }
  if (diffHours < 24) return `Due in ${Math.max(1, Math.round(diffHours))}h`;
  return `Due in ${Math.round(diffHours / 24)}d`;
}

export function JobCard({ job }: { job: VendorJob }) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <Link href={`/vendor/jobs/${job.id}`} className="font-medium text-ink hover:text-teal">
            {job.siteName}
          </Link>
          <p className="mt-0.5 text-xs text-ink-soft">{siteTypeLabel(job.siteType)}</p>
        </div>
        <SlaBadge status={job.status} />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-ink-soft">
        <span className="flex items-center gap-1">
          <MapPin size={13} strokeWidth={1.75} aria-hidden="true" />
          {job.district}, {job.state} · {job.distanceKm.toFixed(1)} km
        </span>
        <span className="flex items-center gap-1">
          <Clock3 size={13} strokeWidth={1.75} aria-hidden="true" />
          {deadlineLabel(job.deadline)}
        </span>
      </div>

      <div className="flex items-center justify-between border-t border-line pt-3">
        <span className="flex items-center gap-1 font-mono tabular text-sm font-semibold text-ink">
          <IndianRupee size={14} strokeWidth={1.75} aria-hidden="true" />
          {job.payoutInr.toLocaleString("en-IN")}
        </span>
        <Link href={`/vendor/jobs/${job.id}`} className="text-sm text-teal hover:underline">
          View job
        </Link>
      </div>
    </Card>
  );
}
