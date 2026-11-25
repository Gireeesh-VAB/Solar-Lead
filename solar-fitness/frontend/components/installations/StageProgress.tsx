// The install pipeline as a connected-dot stepper. Same visual language
// as the check's processing screen (ProcessingClient.tsx) — a filled
// circle for done, a ringed one for current, hollow for pending, joined
// by a rail that colours in behind progress.
//
// Deliberately driven by the `stages` array the BACKEND sends on every
// project rather than a hardcoded list: repositories/installations.py
// owns the pipeline order, and this component owns nothing but the
// pixels. Labels come from INSTALLATION_STAGE_LABEL, so an unrecognised
// key still renders (as its raw key) instead of blanking the row.

import { Check } from "lucide-react";
import { INSTALLATION_STAGE_LABEL } from "@/lib/types";
import { cn } from "@/lib/utils";

export function stageLabel(stage: string): string {
  return INSTALLATION_STAGE_LABEL[stage] ?? stage;
}

export function StageProgress({
  stages,
  stageIndex,
  className,
  compact = false,
}: {
  stages: string[];
  /** -1 when the project's status isn't a known stage — every dot then
   *  renders as pending rather than the component throwing. */
  stageIndex: number;
  className?: string;
  /** Horizontal rail + a single current label, for the customer's
   *  result page where a 16-row vertical list would dominate. */
  compact?: boolean;
}) {
  const total = stages.length;
  const done = Math.max(0, stageIndex);
  const percent = total > 1 ? Math.round((done / (total - 1)) * 100) : 0;

  if (compact) {
    return (
      <div className={cn("space-y-2", className)}>
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-sm font-medium text-ink">
            {stageIndex >= 0 ? stageLabel(stages[stageIndex]) : "Not started"}
          </span>
          <span className="text-xs tabular-nums text-ink-faint">
            Step {Math.max(1, stageIndex + 1)} of {total}
          </span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-line"
          role="progressbar"
          aria-valuenow={percent}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Installation progress"
        >
          <div
            className="h-full rounded-full bg-brand transition-[width] duration-700 ease-out"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>
    );
  }

  return (
    <ol className={cn("text-left", className)} aria-label="Installation stages">
      {stages.map((stage, i) => {
        const isDone = i < stageIndex;
        const isCurrent = i === stageIndex;
        const isLast = i === total - 1;
        return (
          <li key={stage} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-colors duration-500",
                  isDone
                    ? "border-brand bg-brand"
                    : isCurrent
                      ? "border-brand bg-paper ring-2 ring-brand/25"
                      : "border-line bg-paper"
                )}
                aria-hidden="true"
              >
                {isDone ? (
                  <Check size={13} strokeWidth={2.5} className="text-white" />
                ) : isCurrent ? (
                  <span className="h-2 w-2 rounded-full bg-brand" />
                ) : null}
              </span>
              {!isLast && (
                <span
                  className={cn(
                    "my-0.5 w-px flex-1 transition-colors duration-700",
                    isDone ? "bg-brand" : "bg-line"
                  )}
                  style={{ minHeight: "0.9rem" }}
                  aria-hidden="true"
                />
              )}
            </div>
            <span
              className={cn(
                "pb-3 text-sm leading-relaxed transition-colors duration-500",
                isDone ? "text-ink-soft" : isCurrent ? "font-medium text-ink" : "text-ink-faint"
              )}
            >
              {stageLabel(stage)}
              {isCurrent && (
                <span className="ml-2 align-middle text-[11px] uppercase tracking-wide text-brand">
                  In progress
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
