import { History, RefreshCw } from "lucide-react";
import type { CacheProvenance } from "@/lib/types";
import { formatDate, cn } from "@/lib/utils";

export function CacheProvenanceBadge({ cache, className }: { cache: CacheProvenance; className?: string }) {
  if (!cache.cacheHit) {
    return (
      <span className={cn("inline-flex items-center gap-1.5 text-xs text-ink-soft", className)}>
        <RefreshCw size={12} strokeWidth={1.75} aria-hidden="true" />
        Freshly assessed
      </span>
    );
  }
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 rounded-[var(--radius-app)] px-2 py-0.5 text-xs", className)}
      style={{ background: "var(--surface-2)", color: "var(--blue)" }}
      title={cache.originalDate ? `Reused from analysis run on ${formatDate(cache.originalDate)}` : undefined}
    >
      <History size={12} strokeWidth={1.75} aria-hidden="true" />
      Reused from {cache.reusedFromAnalysisId}
      {cache.originalDate && <span className="font-mono">· {formatDate(cache.originalDate)}</span>}
    </span>
  );
}
