"use client";

// engine/panel_packing.py's real packed layout, plus engine/
// panel_validation.py's independent re-check (the `validation` block) —
// surfaced as a trust signal: this isn't just "here's a panel count",
// it's "here's how many candidate positions were rejected and why,
// verified against the actual roof polygon." Reuses useCheckSolarLayout's
// own query key, no extra network request beyond what ResultMap fetches.

import { Grid3x3 } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { useCheckSolarLayout } from "@/lib/query/hooks";
import { useT } from "@/lib/i18n/LanguageContext";

export function PanelLayoutCard({ checkId }: { checkId: string }) {
  const { t } = useT();
  const { data } = useCheckSolarLayout(checkId);
  if (!data || data.status !== "ok" || data.panels.length === 0) return null;

  const orientation = data.panels[0]?.orientation;
  const validation = data.validation;
  const candidates = validation ? validation.panelCount + validation.rejectedCount : null;
  const placedPct = candidates && candidates > 0 ? (validation!.panelCount / candidates) * 100 : null;

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">🔲</span>
        <p className="text-sm font-semibold text-ink">{t("result.panelsTitle", "Solar panels on your roof")}</p>
      </div>
      <p className="mb-3 text-sm text-ink-soft">
        {t("result.panelsDescription", "We can fit {count} solar panels on your roof.", { count: data.panelCount })}
      </p>

      <div className="flex items-center gap-3">
        <span
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
          style={{ background: "var(--surface-2)", color: "var(--blue)" }}
          aria-hidden="true"
        >
          <Grid3x3 size={19} strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <p className="text-lg font-semibold leading-tight tabular text-ink">
            {data.panelCount} panels · {data.totalKwp.toFixed(1)} kW
          </p>
          {orientation && <p className="truncate text-xs capitalize text-ink-faint">{orientation.toLowerCase()} arrangement</p>}
        </div>
      </div>

      {validation && (
        <TechnicalDetails label="Panel placement details">
          {placedPct != null && (
            <div
              role="img"
              aria-label={`${validation.panelCount} of ${candidates} candidate panel positions placed`}
            >
              <div className="flex items-center justify-between text-xs">
                <span className="text-ink-soft">Candidate positions placed</span>
                <span className="font-medium tabular text-ink">
                  {validation.panelCount} / {candidates}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
                <div
                  className="h-full rounded-full transition-[width] duration-500"
                  style={{ width: `${placedPct}%`, background: "var(--good)" }}
                />
              </div>
            </div>
          )}
          <p className="mt-2.5 text-xs text-ink-faint">
            {validation.rejectedCount > 0 &&
              `${validation.rejectedCount} rejected for not fitting the usable roof shape. `}
            Verified: {validation.panelsOutsideRoof} outside the roof boundary, {validation.panelsIntersectingObstacles} overlapping an obstacle.
          </p>
        </TechnicalDetails>
      )}
    </Card>
  );
}
