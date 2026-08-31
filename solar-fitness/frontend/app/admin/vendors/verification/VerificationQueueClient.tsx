"use client";

import { useState } from "react";
import { useVendorVerificationDecision, useVendorVerificationQueue } from "@/lib/query/hooks";
import { Card, TableSkeleton, ErrorState, EmptyState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import type { AdminVendorSummary } from "@/lib/types";

export function VerificationQueueClient() {
  const queue = useVendorVerificationQueue();
  const decide = useVendorVerificationDecision();
  const [approveTarget, setApproveTarget] = useState<AdminVendorSummary | null>(null);
  const [rejectTarget, setRejectTarget] = useState<AdminVendorSummary | null>(null);

  if (queue.isLoading) return <TableSkeleton rows={3} cols={4} />;
  if (queue.isError || !queue.data) return <ErrorState description="Could not load verification queue." onRetry={() => queue.refetch()} />;
  if (queue.data.length === 0) {
    return (
      <EmptyState
        icon={<ShieldCheck size={28} strokeWidth={1.5} />}
        title="No vendors awaiting verification"
        description="New vendor sign-ups requiring review will appear here."
      />
    );
  }

  return (
    <div className="space-y-3">
      {queue.data.map((v) => (
        <Card key={v.id} className="p-4">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="font-medium text-ink">{v.name}</p>
              <p className="text-xs text-ink-soft">
                {v.serviceArea} · applied {formatDate(v.joinedAt)} · payout via {v.payoutMethod}
              </p>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setApproveTarget(v)} disabled={decide.isPending}>
              <CheckCircle2 size={14} strokeWidth={1.75} /> Approve
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setRejectTarget(v)} disabled={decide.isPending}>
              <XCircle size={14} strokeWidth={1.75} /> Reject
            </Button>
          </div>
        </Card>
      ))}

      <ConfirmDialog
        open={!!approveTarget}
        title={approveTarget ? `Approve ${approveTarget.name}?` : ""}
        description="This onboards the vendor onto the platform and makes them eligible for job assignment immediately."
        confirmLabel="Approve vendor"
        tone="primary"
        pending={decide.isPending}
        onCancel={() => setApproveTarget(null)}
        onConfirm={() =>
          approveTarget &&
          decide.mutate({ id: approveTarget.id, decision: "approve" }, { onSuccess: () => setApproveTarget(null) })
        }
      />
      <ConfirmDialog
        open={!!rejectTarget}
        title={rejectTarget ? `Reject ${rejectTarget.name}?` : ""}
        description="The vendor will not be onboarded onto the platform. They may reapply later."
        confirmLabel="Reject vendor"
        tone="danger"
        pending={decide.isPending}
        onCancel={() => setRejectTarget(null)}
        onConfirm={() =>
          rejectTarget &&
          decide.mutate({ id: rejectTarget.id, decision: "reject" }, { onSuccess: () => setRejectTarget(null) })
        }
      />
    </div>
  );
}
