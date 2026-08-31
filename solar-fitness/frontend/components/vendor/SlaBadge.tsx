import type { VendorJobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const VENDOR_STATUS_LABEL: Record<VendorJobStatus, string> = {
  queued: "Queued",
  accepted: "Accepted",
  in_progress: "In progress",
  submitted: "Submitted",
  sla_at_risk: "SLA at risk",
  overdue: "Overdue",
};

const STYLE: Record<VendorJobStatus, { bg: string; fg: string }> = {
  queued: { bg: "var(--neutral-bg)", fg: "var(--neutral-verdict)" },
  accepted: { bg: "var(--surface-2)", fg: "var(--teal)" },
  in_progress: { bg: "var(--surface-2)", fg: "var(--blue)" },
  submitted: { bg: "var(--good-bg)", fg: "var(--good)" },
  sla_at_risk: { bg: "var(--warn-bg)", fg: "var(--warn)" },
  overdue: { bg: "var(--bad-bg)", fg: "var(--bad)" },
};

export function SlaBadge({ status, className }: { status: VendorJobStatus; className?: string }) {
  const { bg, fg } = STYLE[status];
  return (
    <span
      className={cn("inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium", className)}
      style={{ background: bg, color: fg }}
    >
      {VENDOR_STATUS_LABEL[status]}
    </span>
  );
}
