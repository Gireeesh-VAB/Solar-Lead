"use client";

import { useState } from "react";
import { useCalibrationDecision, useCalibrationProposals } from "@/lib/query/hooks";
import { Card, TableSkeleton, ErrorState, EmptyState, Button, Badge } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { CalibrationProposal } from "@/lib/types";
import { CheckCircle2, Gauge, XCircle } from "lucide-react";

export function AdminCalibrationClient() {
  const proposals = useCalibrationProposals();
  const decide = useCalibrationDecision();
  const [approveTarget, setApproveTarget] = useState<CalibrationProposal | null>(null);
  const [rejectTarget, setRejectTarget] = useState<CalibrationProposal | null>(null);

  if (proposals.isLoading) return <TableSkeleton rows={3} cols={4} />;
  if (proposals.isError || !proposals.data) return <ErrorState description="Could not load calibration proposals." onRetry={() => proposals.refetch()} />;

  const pending = proposals.data.filter((p) => p.status === "pending_approval");
  const decided = proposals.data.filter((p) => p.status !== "pending_approval");

  return (
    <div className="space-y-6">
      {pending.length === 0 && (
        <EmptyState icon={<Gauge size={28} strokeWidth={1.5} />} title="No proposals pending approval" description="New recalibration proposals from field variance will appear here." />
      )}
      <div className="space-y-3">
        {pending.map((p) => (
          <Card key={p.id} className="p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-medium text-ink">{p.metric}</p>
                <p className="text-xs text-ink-soft">
                  {p.jurisdiction} · sample size {p.sampleSize} · proposed {formatDate(p.proposedAt)}
                </p>
              </div>
              <Badge tone="amber">pending approval</Badge>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
              <div>
                <p className="text-xs text-ink-faint">Remote value</p>
                <p className="font-mono tabular text-ink">{p.remoteValue}</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">Measured value</p>
                <p className="font-mono tabular text-ink">{p.measuredValue}</p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">Variance</p>
                <p className="font-mono tabular" style={{ color: Math.abs(p.variancePct) > 10 ? "var(--bad)" : "var(--good)" }}>
                  {p.variancePct > 0 ? "+" : ""}
                  {p.variancePct}%
                </p>
              </div>
            </div>
            <p className="mt-3 text-sm text-ink">{p.proposedAdjustment}</p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" onClick={() => setApproveTarget(p)} disabled={decide.isPending}>
                <CheckCircle2 size={14} strokeWidth={1.75} /> Approve
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setRejectTarget(p)} disabled={decide.isPending}>
                <XCircle size={14} strokeWidth={1.75} /> Reject
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {decided.length > 0 && (
        <section aria-labelledby="calibration-history-heading">
          <h2 id="calibration-history-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
            History
          </h2>
          <div className="space-y-2">
            {decided.map((p) => (
              <Card key={p.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <span className="text-sm text-ink">{p.metric} · {p.jurisdiction}</span>
                <Badge tone={p.status === "approved" ? "blue" : "neutral"}>{p.status}</Badge>
              </Card>
            ))}
          </div>
        </section>
      )}

      <ConfirmDialog
        open={!!approveTarget}
        title={approveTarget ? `Approve recalibration for ${approveTarget.metric}?` : ""}
        description="This applies the proposed adjustment to production assumptions for this jurisdiction. This action cannot be undone from this screen."
        confirmLabel="Approve"
        tone="danger"
        pending={decide.isPending}
        onCancel={() => setApproveTarget(null)}
        onConfirm={() =>
          approveTarget &&
          decide.mutate({ id: approveTarget.id, decision: "approve" }, { onSuccess: () => setApproveTarget(null) })
        }
      />
      <ConfirmDialog
        open={!!rejectTarget}
        title={rejectTarget ? `Reject recalibration for ${rejectTarget.metric}?` : ""}
        description="The proposed adjustment will not be applied. It can be resubmitted later with new field data."
        confirmLabel="Reject"
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
