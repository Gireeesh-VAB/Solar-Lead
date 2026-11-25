"use client";

// The 5 real factors behind SuitabilityScoreCard's "Analysis confidence"
// figure — engine/fitness.py::score_fitness()'s own
// FitnessResult.confidence_components (FIT-04). Each is null when that
// factor's input was unavailable; rendered as "Not available", never 0%,
// same discipline ScoreBreakdownList already applies to its own 5 score
// factors.
//
// confidenceExplanation is deterministic, template-generated text from
// engine/fitness.py::_explain_confidence() — never free-form/AI-written
// — index 0 is always the overall summary sentence, the rest are one
// sentence per factor, already ordered by how much it contributed.

import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import type { Assessment, ConfidenceComponents } from "@/lib/types";

const FACTOR_LABEL: Record<keyof ConfidenceComponents, string> = {
  geometry: "Roof boundary & geometry data",
  imageryRecency: "Imagery recency",
  constraintCompleteness: "Constraint data completeness",
  gateResolution: "Site-check resolution",
  calibrationState: "Field-calibration accuracy",
  ceilingDelta: "Constraint-specific adjustments",
};

const FACTOR_ORDER: (keyof ConfidenceComponents)[] = [
  "geometry",
  "imageryRecency",
  "constraintCompleteness",
  "gateResolution",
  "calibrationState",
];

export function ConfidenceBreakdownList({ assessment }: { assessment: Assessment }) {
  const components = assessment.confidenceComponents ?? {};
  const explanation = assessment.confidenceExplanation ?? [];

  const hasAnyComponent = FACTOR_ORDER.some((key) => components[key] != null);
  if (!hasAnyComponent) return null;

  const [summary, ...factorSentences] = explanation;

  return (
    <Card className="p-4">
      <p className="mb-1 text-sm font-semibold text-ink">Why this confidence score</p>
      <p className="mb-3 text-sm text-ink-soft">
        {summary ?? "Five things go into how sure we are about this result — see them below if you're curious."}
      </p>

      <TechnicalDetails label="Confidence breakdown">
        <div className="space-y-4">
          <ul className="space-y-2.5">
            {FACTOR_ORDER.map((key) => {
              const value = components[key];
              const percent = value != null ? Math.round(value * 100) : null;
              return (
                <li key={key}>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-ink-soft">{FACTOR_LABEL[key]}</span>
                    <span className="font-medium text-ink tabular">
                      {percent != null ? `${percent}%` : "Not available"}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
                    {percent != null && (
                      <div
                        className="h-full rounded-full bg-blue transition-[width] duration-500"
                        style={{ width: `${percent}%` }}
                      />
                    )}
                  </div>
                </li>
              );
            })}
          </ul>

          {factorSentences.length > 0 && (
            <ul className="space-y-1.5 text-sm text-ink-soft">
              {factorSentences.map((sentence) => (
                <li key={sentence}>{sentence}</li>
              ))}
            </ul>
          )}
        </div>
      </TechnicalDetails>
    </Card>
  );
}
