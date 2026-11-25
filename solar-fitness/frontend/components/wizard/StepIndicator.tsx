"use client";

// The one genuinely new piece of chrome StartCheckWizard needed: nothing
// in this codebase previously told a customer "where am I in this flow"
// across a multi-step process (a grep for stepper/wizard turned up
// nothing). Built from the same design tokens/cn() every other component
// here uses — no new dependency, `framer-motion` (already a dependency)
// only for the active-step fill transition.

import { motion } from "framer-motion";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface WizardStepMeta {
  key: string;
  label: string;
}

export function StepIndicator({
  steps,
  currentIndex,
}: {
  steps: WizardStepMeta[];
  /** Index into `steps` of the step currently shown. Every index before
   *  it reads as completed. */
  currentIndex: number;
}) {
  return (
    <div className="w-full">
      {/* Desktop/tablet: full horizontal stepper with labels. */}
      <ol className="hidden items-center gap-2 sm:flex">
        {steps.map((step, i) => {
          const done = i < currentIndex;
          const active = i === currentIndex;
          return (
            <li key={step.key} className="flex flex-1 items-center gap-2 last:flex-none">
              <div className="flex items-center gap-2">
                <span
                  className={cn(
                    "flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold transition-colors",
                    done && "bg-blue text-white",
                    active && !done && "border-2 border-blue text-blue",
                    !active && !done && "border border-line text-ink-faint"
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  {done ? <Check size={13} strokeWidth={2.5} aria-hidden="true" /> : i + 1}
                </span>
                <span
                  className={cn(
                    "text-xs font-medium",
                    active ? "text-ink" : done ? "text-ink-soft" : "text-ink-faint"
                  )}
                >
                  {step.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <span className="h-px flex-1 bg-line" aria-hidden="true">
                  <motion.span
                    className="block h-px bg-blue"
                    initial={false}
                    animate={{ width: done ? "100%" : "0%" }}
                    transition={{ duration: 0.3 }}
                  />
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {/* Mobile: condensed progress bar + "Step N of M" label. */}
      <div className="sm:hidden">
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="font-medium text-ink">{steps[currentIndex]?.label}</span>
          <span className="text-ink-faint">
            Step {currentIndex + 1} of {steps.length}
          </span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2">
          <motion.div
            className="h-full rounded-full bg-blue"
            initial={false}
            animate={{ width: `${((currentIndex + 1) / steps.length) * 100}%` }}
            transition={{ duration: 0.3 }}
          />
        </div>
      </div>
    </div>
  );
}
