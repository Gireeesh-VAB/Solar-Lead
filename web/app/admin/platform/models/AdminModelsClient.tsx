"use client";

import { useState } from "react";
import { useModelVersionDecision, useModelVersions } from "@/lib/query/hooks";
import { Card, TableSkeleton, ErrorState, EmptyState, Button, Badge } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { ModelVersionProposal } from "@/lib/types";
import { CheckCircle2, Gauge, PauseCircle } from "lucide-react";

function ModelCard({ version, label }: { version: ModelVersionProposal | undefined; label: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">{label}</p>
      {version ? (
        <>
          <p className="mt-1 font-mono tabular font-medium text-ink">
            {version.modelName} v{version.version}
          </p>
          <p className="text-xs text-ink-soft">
            {version.proposedBy} · {formatDate(version.proposedAt)}
          </p>
          <p className="mt-2 text-sm text-ink">{version.changelog}</p>
          <div className="mt-3 space-y-1.5">
            {version.metrics.map((m) => (
              <div key={m.label} className="flex items-center justify-between text-xs">
                <span className="text-ink-faint">{m.label}</span>
                <span className="font-mono tabular text-ink">{m.value}</span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="mt-2 text-sm text-ink-faint">None</p>
      )}
    </Card>
  );
}

export function AdminModelsClient() {
  const versions = useModelVersions();
  const decide = useModelVersionDecision();
  const [approveTarget, setApproveTarget] = useState<ModelVersionProposal | null>(null);
  const [holdTarget, setHoldTarget] = useState<ModelVersionProposal | null>(null);

  if (versions.isLoading) return <TableSkeleton rows={3} cols={4} />;
  if (versions.isError || !versions.data) return <ErrorState description="Could not load model versions." onRetry={() => versions.refetch()} />;
  if (versions.data.length === 0) return <EmptyState icon={<Gauge size={28} strokeWidth={1.5} />} title="No model versions on file" />;

  const active = versions.data.find((v) => v.status === "active");
  const proposed = versions.data.filter((v) => v.status === "proposed");
  const history = versions.data.filter((v) => v.status !== "active" && v.status !== "proposed");

  return (
    <div className="space-y-6">
      {proposed.map((candidate) => (
        <section key={candidate.id} aria-labelledby={`compare-${candidate.id}`}>
          <h2 id={`compare-${candidate.id}`} className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
            Candidate v{candidate.version} vs. active
          </h2>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ModelCard version={active} label="Active (production)" />
            <ModelCard version={candidate} label="Candidate (proposed)" />
          </div>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => setApproveTarget(candidate)} disabled={decide.isPending}>
              <CheckCircle2 size={14} strokeWidth={1.75} /> Approve &amp; promote to active
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setHoldTarget(candidate)} disabled={decide.isPending}>
              <PauseCircle size={14} strokeWidth={1.75} /> Hold / reject
            </Button>
          </div>
        </section>
      ))}

      {proposed.length === 0 && (
        <EmptyState icon={<Gauge size={28} strokeWidth={1.5} />} title="No candidate versions pending review" description="New model proposals from the ML platform team will appear here." />
      )}

      {history.length > 0 && (
        <section aria-labelledby="model-history-heading">
          <h2 id="model-history-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
            History
          </h2>
          <div className="space-y-2">
            {history.map((v) => (
              <Card key={v.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <span className="font-mono tabular text-sm text-ink">
                  {v.modelName} v{v.version}
                </span>
                <Badge tone="neutral">{v.status}</Badge>
              </Card>
            ))}
          </div>
        </section>
      )}

      <ConfirmDialog
        open={!!approveTarget}
        title={approveTarget ? `Promote v${approveTarget.version} to active?` : ""}
        description="This replaces the current production model for all new assessments platform-wide. This action cannot be undone from this screen."
        confirmLabel="Approve & promote"
        tone="danger"
        pending={decide.isPending}
        onCancel={() => setApproveTarget(null)}
        onConfirm={() =>
          approveTarget &&
          decide.mutate({ id: approveTarget.id, decision: "approve" }, { onSuccess: () => setApproveTarget(null) })
        }
      />
      <ConfirmDialog
        open={!!holdTarget}
        title={holdTarget ? `Reject v${holdTarget.version}?` : ""}
        description="This candidate will not be promoted to production. It can be resubmitted later as a new proposal."
        confirmLabel="Hold / reject"
        tone="danger"
        pending={decide.isPending}
        onCancel={() => setHoldTarget(null)}
        onConfirm={() =>
          holdTarget && decide.mutate({ id: holdTarget.id, decision: "reject" }, { onSuccess: () => setHoldTarget(null) })
        }
      />
    </div>
  );
}
