"use client";

// The 5 real factors behind SuitabilityScoreCard's blended score —
// engine/fitness.py::score_fitness()'s own FitnessResult.components.
// Each is null when that factor's input was unavailable; rendered as
// "Not available", never 0%, since 0 and "we didn't check" mean
// opposite things (same discipline CalculationBreakdown already
// applies to ceiling kWp values).
//
// Below the 5 scored components, a separate "Roof data" section shows
// RAW, UNSCORED per-segment orientation/tilt — there is no real
// per-item score for orientation, tilt, roof condition, or obstruction
// severity anywhere in the engine, so none is invented here.

import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { compassDirection, parseRoofSegments, type Assessment, type ScoreComponents } from "@/lib/types";

const COMPONENT_LABEL: Record<keyof ScoreComponents, string> = {
  capacityAdequacy: "Capacity adequacy",
  constraintHeadroom: "Constraint headroom",
  geometryQuality: "Roof boundary confidence",
  shading: "Shading impact",
  generationYield: "Generation yield",
};

const COMPONENT_ORDER: (keyof ScoreComponents)[] = [
  "capacityAdequacy",
  "constraintHeadroom",
  "geometryQuality",
  "shading",
  "generationYield",
];

export function ScoreBreakdownList({ assessment }: { assessment: Assessment }) {
  const components = assessment.scoreComponents ?? {};
  const segments = parseRoofSegments(assessment.roofSegments);

  const hasAnyComponent = COMPONENT_ORDER.some((key) => components[key] != null);
  if (!hasAnyComponent && segments.length === 0) return null;

  return (
    <Card className="p-4">
      <p className="mb-1 text-sm font-semibold text-ink">How your score was worked out</p>
      <p className="mb-3 text-sm text-ink-soft">Five things go into your score — see them below if you&apos;re curious.</p>

      <TechnicalDetails label="Score breakdown">
        <div className="space-y-4">
          {hasAnyComponent && (
            <ul className="space-y-2.5">
              {COMPONENT_ORDER.map((key) => {
                const value = components[key];
                const percent = value != null ? Math.round(value * 100) : null;
                return (
                  <li key={key}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-ink-soft">{COMPONENT_LABEL[key]}</span>
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
          )}

          {segments.length > 0 && (
            <div>
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
                Roof data (descriptive, not scored)
              </p>
              <ul className="space-y-1.5">
                {segments.map((segment) => (
                  <li key={segment.segmentIndex} className="flex items-center justify-between text-sm">
                    <span className="text-ink-soft">
                      {segments.length > 1 ? `Section ${segment.segmentIndex + 1}` : "Orientation"}
                      {segment.azimuthDeg != null &&
                        ` — facing ${compassDirection(segment.azimuthDeg)} (${Math.round(segment.azimuthDeg)}°)`}
                    </span>
                    <span className="font-medium text-ink">
                      {segment.pitchDeg != null ? `${Math.round(segment.pitchDeg)}° tilt` : "—"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </TechnicalDetails>
    </Card>
  );
}
