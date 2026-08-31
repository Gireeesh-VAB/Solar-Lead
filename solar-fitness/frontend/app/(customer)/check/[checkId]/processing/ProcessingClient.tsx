"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCompleteCheck } from "@/lib/query/hooks";

const STEPS = [
  "Locating your site",
  "Checking imagery",
  "Evaluating suitability",
  "Preparing your result",
];

const STEP_DURATION_MS = 750; // ~3s total across 4 steps, within the 2-4s target

export function ProcessingClient({ checkId }: { checkId: string }) {
  const router = useRouter();
  const completeCheck = useCompleteCheck(checkId);
  const [activeStep, setActiveStep] = useState(0);

  useEffect(() => {
    if (activeStep >= STEPS.length) return;
    const timer = setTimeout(() => setActiveStep((s) => s + 1), STEP_DURATION_MS);
    return () => clearTimeout(timer);
  }, [activeStep]);

  useEffect(() => {
    if (activeStep < STEPS.length) return;
    let cancelled = false;
    completeCheck.mutateAsync().then(() => {
      if (!cancelled) router.replace(`/check/${checkId}/result`);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeStep]);

  return (
    <div className="mx-auto flex max-w-sm flex-col items-center gap-6 py-16 text-center">
      <Loader2 size={32} strokeWidth={1.75} className="animate-spin text-amber" aria-hidden="true" />
      <div>
        <h1 className="text-lg font-semibold text-ink">Checking your location</h1>
        <p className="mt-1 text-sm text-ink-soft">This usually takes less than a minute.</p>
      </div>
      <ol className="w-full space-y-2.5 text-left" aria-live="polite">
        {STEPS.map((label, i) => {
          const done = i < activeStep;
          const current = i === activeStep;
          return (
            <li key={label} className="flex items-center gap-2.5 text-sm">
              {done ? (
                <CheckCircle2 size={16} strokeWidth={1.75} className="shrink-0" style={{ color: "var(--good)" }} aria-hidden="true" />
              ) : current ? (
                <Loader2 size={16} strokeWidth={1.75} className="shrink-0 animate-spin text-blue" aria-hidden="true" />
              ) : (
                <span className="h-4 w-4 shrink-0 rounded-full border border-line" aria-hidden="true" />
              )}
              <span className={cn(done ? "text-ink-soft" : current ? "font-medium text-ink" : "text-ink-faint")}>{label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
