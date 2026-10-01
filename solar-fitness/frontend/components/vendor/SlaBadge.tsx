import type { VendorJobStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export const VENDOR_STATUS_LABEL: Record<VendorJobStatus, string> = {
  queued: "Queued",
  accepted: "Accepted",
  in_progress: "In progress",
  submitted: "Submitted",
  sla_at_risk: "SLA at risk",
  overdue: "Overdue",
  declined: "Declined",
};

// Deliberately NOT rendered through <Badge tone=…>: the SLA ladder has
// six distinct visual states and Badge offers five tones, so queued /
// accepted / in_progress / submitted would collapse onto each other and
// "SLA at risk" would lose its filled --warn-bg emphasis (Badge's amber
// is a tint on --surface-2). `cn()` is a plain join with no
// tailwind-merge, so overriding Badge's tone classes per status isn't
// reliable either. What this DOES share with Badge is the vocabulary:
// every pair below is one of Badge's own semantic token pairs, with
// --teal kept only as the secondary accent for the mid-flight "accepted"
// state now that --brand/--good is the primary green.
const STYLE: Record<VendorJobStatus, { bg: string; fg: string }> = {
  queued: { bg: "var(--surface-2)", fg: "var(--ink-soft)" },
  accepted: { bg: "var(--surface-2)", fg: "var(--teal)" },
  in_progress: { bg: "var(--surface-2)", fg: "var(--blue)" },
  submitted: { bg: "var(--good-bg)", fg: "var(--good)" },
  sla_at_risk: { bg: "var(--warn-bg)", fg: "var(--warn)" },
  overdue: { bg: "var(--bad-bg)", fg: "var(--bad)" },
  declined: { bg: "var(--bad-bg)", fg: "var(--bad)" },
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
