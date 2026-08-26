"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, PlayCircle, XCircle } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { useVendorJobAction } from "@/lib/query/hooks";
import type { VendorJob } from "@/lib/types";

export function JobActions({ job }: { job: VendorJob }) {
  const router = useRouter();
  const action = useVendorJobAction(job.id);

  if (job.status === "queued") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => action.mutate("accept")} disabled={action.isPending}>
          <CheckCircle2 size={15} strokeWidth={1.75} /> {action.isPending ? "Accepting…" : "Accept job"}
        </Button>
        <Button
          variant="danger"
          onClick={() => action.mutate("decline", { onSuccess: () => router.push("/vendor/jobs") })}
          disabled={action.isPending}
        >
          <XCircle size={15} strokeWidth={1.75} /> Decline
        </Button>
      </div>
    );
  }

  if (job.status === "accepted" || job.status === "sla_at_risk" || job.status === "overdue") {
    return (
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => action.mutate("start")} disabled={action.isPending}>
          <PlayCircle size={15} strokeWidth={1.75} /> {action.isPending ? "Starting…" : "Start job"}
        </Button>
        <Link href={`/vendor/jobs/${job.id}/capture`}>
          <Button variant="secondary">Go to capture</Button>
        </Link>
      </div>
    );
  }

  if (job.status === "in_progress") {
    return (
      <Link href={`/vendor/jobs/${job.id}/capture`}>
        <Button>Continue capture</Button>
      </Link>
    );
  }

  return null;
}
