"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, PlayCircle, Send, XCircle } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { useVendorJobAction } from "@/lib/query/hooks";
import type { VendorJob } from "@/lib/types";

export function JobActions({ job }: { job: VendorJob }) {
  const router = useRouter();
  const action = useVendorJobAction(job.id);

  // A failed action (e.g. this job was already started/submitted from
  // another device — status transitions are enforced server-side and
  // reported as a 409) previously failed completely silently: the
  // button just reverted with no explanation. Same inline-error
  // convention as AssessmentReviewClient.tsx/AssessmentFeasibilityClient.tsx.
  const errorNotice = action.isError && (
    <p className="w-full text-xs text-bad">{(action.error as Error).message}</p>
  );

  // This page (app/vendor/jobs/[jobId]/page.tsx) is a Server Component —
  // `job` is fetched once at request time, not read from a client-side
  // query, so React Query's own cache invalidation inside
  // useVendorJobAction has nothing here to refetch. Without this, the
  // status only ever updated on a manual reload/navigation, even though
  // the mutation itself had already succeeded. router.refresh() re-runs
  // the server fetch in place and re-renders with the new `job` prop.
  const refresh = () => router.refresh();

  if (job.status === "queued") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => action.mutate("accept", { onSuccess: refresh })} disabled={action.isPending}>
          <CheckCircle2 size={15} strokeWidth={1.75} /> {action.isPending ? "Accepting…" : "Accept job"}
        </Button>
        <Button
          variant="danger"
          onClick={() => action.mutate("decline", { onSuccess: () => router.push("/vendor/jobs") })}
          disabled={action.isPending}
        >
          <XCircle size={15} strokeWidth={1.75} /> Decline
        </Button>
        {errorNotice}
      </div>
    );
  }

  if (job.status === "accepted" || job.status === "sla_at_risk" || job.status === "overdue") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => action.mutate("start", { onSuccess: refresh })} disabled={action.isPending}>
          <PlayCircle size={15} strokeWidth={1.75} /> {action.isPending ? "Starting…" : "Start job"}
        </Button>
        <Link href={`/vendor/jobs/${job.id}/capture`}>
          <Button variant="secondary">Go to capture</Button>
        </Link>
        {errorNotice}
      </div>
    );
  }

  if (job.status === "in_progress") {
    return (
      <div className="flex flex-wrap gap-2">
        <Link href={`/vendor/jobs/${job.id}/capture`}>
          <Button variant="secondary">Continue capture</Button>
        </Link>
        {/* Nothing here validates that the six survey sections were
            actually filled in first — a real, known gap, not a silent
            omission. */}
        <Button
          onClick={() => action.mutate("submit", { onSuccess: () => router.push("/vendor/jobs") })}
          disabled={action.isPending}
        >
          <Send size={15} strokeWidth={1.75} /> {action.isPending ? "Submitting…" : "Submit survey"}
        </Button>
        {errorNotice}
      </div>
    );
  }

  return null;
}
