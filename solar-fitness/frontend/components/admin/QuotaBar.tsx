import type { ApiQuota } from "@/lib/types";

export function QuotaBar({ quota }: { quota: ApiQuota }) {
  const pct = Math.min(100, Math.round((quota.used / quota.limit) * 100));
  const warning = pct >= 85;
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="font-medium text-ink">{quota.service}</span>
        <span className="font-mono tabular" style={{ color: warning ? "var(--bad)" : "var(--ink-soft)" }}>
          {quota.used.toLocaleString("en-IN")} / {quota.limit.toLocaleString("en-IN")} {quota.unit}
        </span>
      </div>
      <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${quota.service} usage`}>
        <div
          className="h-full rounded-full transition-[width]"
          style={{ width: `${pct}%`, background: warning ? "var(--bad)" : "var(--slate)" }}
        />
      </div>
      {warning && <p className="mt-1 text-[11px]" style={{ color: "var(--bad)" }}>Approaching quota limit ({pct}% used)</p>}
    </div>
  );
}
