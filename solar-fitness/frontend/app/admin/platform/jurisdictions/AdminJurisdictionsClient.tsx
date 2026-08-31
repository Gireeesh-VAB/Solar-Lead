"use client";

import { useState } from "react";
import { useJurisdictions } from "@/lib/query/hooks";
import { TableSkeleton, ErrorState, EmptyState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { formatDate } from "@/lib/utils";
import type { JurisdictionConstraintPack } from "@/lib/types";
import { Gauge, UploadCloud } from "lucide-react";

export function AdminJurisdictionsClient() {
  const jurisdictions = useJurisdictions();
  const [publishTarget, setPublishTarget] = useState<JurisdictionConstraintPack | null>(null);
  const [publishing, setPublishing] = useState(false);
  const [justPublished, setJustPublished] = useState<string | null>(null);

  if (jurisdictions.isLoading) return <TableSkeleton rows={4} cols={5} />;
  if (jurisdictions.isError || !jurisdictions.data) return <ErrorState description="Could not load jurisdiction packs." onRetry={() => jurisdictions.refetch()} />;
  if (jurisdictions.data.length === 0) {
    return <EmptyState icon={<Gauge size={28} strokeWidth={1.5} />} title="No jurisdiction packs configured" />;
  }

  function handlePublish() {
    setPublishing(true);
    // Mock async publish — no server mutation exists for jurisdictions yet, so
    // this simulates the round trip and reports success locally.
    setTimeout(() => {
      setPublishing(false);
      setJustPublished(publishTarget?.id ?? null);
      setPublishTarget(null);
    }, 500);
  }

  return (
    <div className="space-y-4">
      {justPublished && (
        <div className="rounded-[var(--radius-app)] border px-3 py-2 text-sm" style={{ borderColor: "var(--good)", background: "var(--good-bg)", color: "var(--good)" }}>
          New version queued for publish — the fitness engine will pick it up on next assessment run.
        </div>
      )}
      <div className="overflow-x-auto scrollbar-thin">
        <table className="w-full min-w-[800px] text-sm">
          <caption className="sr-only">Jurisdiction constraint pack versions</caption>
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
              <th scope="col" className="py-2 pr-3 font-medium">Jurisdiction</th>
              <th scope="col" className="py-2 pr-3 font-medium">State</th>
              <th scope="col" className="py-2 pr-3 font-medium">Version</th>
              <th scope="col" className="py-2 pr-3 font-medium">Rules</th>
              <th scope="col" className="py-2 pr-3 font-medium">Updated</th>
              <th scope="col" className="py-2 pr-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {jurisdictions.data.map((pack, i) => (
              <tr key={pack.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
                <td className="py-2.5 pr-3 font-medium text-ink">{pack.jurisdiction}</td>
                <td className="py-2.5 pr-3 text-ink-soft">{pack.state}</td>
                <td className="py-2.5 pr-3 font-mono tabular text-ink">v{pack.version}</td>
                <td className="py-2.5 pr-3 font-mono tabular text-ink">{pack.rules.length}</td>
                <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(pack.updatedAt)}</td>
                <td className="py-2.5 pr-3">
                  <Button size="sm" variant="secondary" onClick={() => setPublishTarget(pack)}>
                    <UploadCloud size={13} strokeWidth={1.75} /> Publish new version
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={!!publishTarget}
        title={publishTarget ? `Publish a new version of ${publishTarget.jurisdiction}?` : ""}
        description="This replaces the active constraint pack used by the fitness engine for all sites in this jurisdiction. Existing assessments are not retroactively recalculated."
        confirmLabel="Publish version"
        tone="danger"
        pending={publishing}
        onCancel={() => setPublishTarget(null)}
        onConfirm={handlePublish}
      />
    </div>
  );
}
