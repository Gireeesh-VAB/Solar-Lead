"use client";

// The report's hero number. engine/fitness.py::score_fitness()'s own
// 0..1 blended score, rescaled to 0-100 purely for a customer-facing
// "X/100" figure — no new calculation happens here. Null exactly when
// verdict is INSUFFICIENT_DATA (FIT-03): rendered as "Not yet scored",
// never a fabricated number standing in for missing data.

import { Card } from "@/components/ui/Primitives";
import { InfoTip } from "@/components/ui/InfoTip";
import type { Verdict } from "@/lib/types";

const SUITABILITY_LABEL: { min: number; label: string }[] = [
  { min: 85, label: "Highly suitable" },
  { min: 65, label: "Suitable" },
  { min: 45, label: "Marginally suitable" },
  { min: 0, label: "Not suitable" },
];

function suitabilityLabel(score: number): string {
  return SUITABILITY_LABEL.find((tier) => score >= tier.min)?.label ?? "Not suitable";
}

// Same arc geometry as the processing page's sizing-system gauge —
// 270-degree sweep, gauge-sweep/counter-tick keyframes reused from
// app/globals.css.
const RADIUS = 46;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS * 0.75;

export function SuitabilityScoreCard({
  score,
  confidenceScore,
  verdict,
}: {
  score: number | null | undefined;
  confidenceScore: number | null | undefined;
  verdict: Verdict;
}) {
  const hasScore = score != null;
  const clamped = hasScore ? Math.max(0, Math.min(100, score)) : 0;
  const dashOffset = CIRCUMFERENCE * (1 - clamped / 100);

  return (
    <Card className="flex items-center gap-5 p-5">
      <div className="relative flex h-28 w-28 shrink-0 items-center justify-center">
        <svg viewBox="0 0 140 140" className="h-full w-full" aria-hidden="true">
          <g transform="rotate(135 70 70)">
            <circle
              cx="70"
              cy="70"
              r={RADIUS}
              fill="none"
              stroke="var(--surface-2)"
              strokeWidth="10"
              strokeLinecap="round"
              strokeDasharray={`${CIRCUMFERENCE} 999`}
            />
            {hasScore && (
              <circle
                cx="70"
                cy="70"
                r={RADIUS}
                fill="none"
                stroke="var(--brand)"
                strokeWidth="10"
                strokeLinecap="round"
                strokeDasharray={`${CIRCUMFERENCE} 999`}
                style={{
                  animation: "gauge-sweep 1.1s cubic-bezier(0.16,1,0.3,1) forwards",
                  ["--gauge-full" as string]: CIRCUMFERENCE,
                  ["--gauge-target" as string]: dashOffset,
                }}
              />
            )}
          </g>
        </svg>
        <div className="absolute flex flex-col items-center">
          {hasScore ? (
            <>
              <span className="text-2xl font-semibold tabular text-ink">{Math.round(score!)}</span>
              <span className="text-[10px] text-ink-faint">/ 100</span>
            </>
          ) : (
            <span className="px-2 text-center text-xs font-medium text-ink-faint">Not yet scored</span>
          )}
        </div>
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Solar suitability score</p>
        <p className="mt-0.5 text-lg font-semibold text-ink">
          {hasScore ? `${Math.round(score!)}/100 — ${suitabilityLabel(score!)}` : "Not yet scored"}
        </p>
        <p className="mt-1 flex items-center gap-1 text-sm text-ink-soft">
          {confidenceScore != null ? (
            <>
              Analysis confidence: {Math.round(confidenceScore)}%
              <InfoTip>How sure we are about this result, based on the quality of the roof data we could find.</InfoTip>
            </>
          ) : (
            "Analysis confidence not available"
          )}
        </p>
        {!hasScore && (
          <p className="mt-1 text-xs text-ink-faint">
            {verdict === "INSUFFICIENT_DATA"
              ? "We don't have enough information yet to give a confident score."
              : "A score wasn't computed for this assessment."}
          </p>
        )}
      </div>
    </Card>
  );
}
