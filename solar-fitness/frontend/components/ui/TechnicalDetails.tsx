"use client";

// The one canonical "Technical details" disclosure — replaces three
// independently-reimplemented collapsible patterns that had drifted
// apart (ScoreBreakdownList, CalculationBreakdown/FinancialCard, and
// Panorama3DToggle each had their own button style). Nothing behind
// this toggle is ever deleted — it's the same data, just demoted below
// the plain-language summary every card now leads with.

import { useState, type ReactNode } from "react";
import { ChevronDown, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export function TechnicalDetails({
  label = "Technical details",
  icon: Icon = SlidersHorizontal,
  defaultOpen = false,
  className,
  children,
}: {
  label?: string;
  icon?: LucideIcon;
  defaultOpen?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className={cn("mt-3", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-[var(--radius-app)] border border-line bg-surface-2 px-3.5 py-2.5 text-left text-sm font-medium text-ink transition-colors hover:bg-surface"
      >
        <span className="flex items-center gap-2">
          <Icon size={15} strokeWidth={1.75} className="text-blue" aria-hidden="true" />
          {label}
        </span>
        <ChevronDown
          size={16}
          strokeWidth={1.75}
          className={cn("text-ink-faint transition-transform", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>
      {open && <div className="mt-2.5">{children}</div>}
    </div>
  );
}
