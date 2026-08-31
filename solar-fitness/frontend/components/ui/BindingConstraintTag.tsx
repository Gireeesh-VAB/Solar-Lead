import { Gavel, HandCoins, Ruler } from "lucide-react";
import type { BindingConstraint, ConstraintKind } from "@/lib/types";
import { CONSTRAINT_KIND_LABEL, cn } from "@/lib/utils";

const KIND_ICON: Record<ConstraintKind, typeof Ruler> = {
  physical: Ruler,
  regulatory: Gavel,
  commercial: HandCoins,
};

export function BindingConstraintTag({
  constraint,
  className,
  showReason = true,
}: {
  constraint: BindingConstraint | null;
  className?: string;
  showReason?: boolean;
}) {
  if (!constraint) {
    return (
      <div className={cn("text-sm text-ink-soft", className)}>
        No binding constraint identified — capacity is set by the highest supportable ceiling.
      </div>
    );
  }
  const Icon = KIND_ICON[constraint.kind];
  return (
    <div className={cn("flex items-start gap-2", className)}>
      <span
        className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-app)]"
        style={{ background: "var(--surface-2)", color: "var(--blue)" }}
        aria-hidden="true"
      >
        <Icon size={14} strokeWidth={1.75} />
      </span>
      <div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="font-medium text-ink">{constraint.name}</span>
          <span
            className="rounded-[3px] px-1.5 py-0.5 text-[11px] uppercase tracking-wide"
            style={{ background: "var(--surface-2)", color: "var(--ink-soft)" }}
          >
            {CONSTRAINT_KIND_LABEL[constraint.kind]}
          </span>
        </div>
        {showReason && <p className="mt-0.5 text-sm text-ink-soft">{constraint.reason}</p>}
      </div>
    </div>
  );
}
