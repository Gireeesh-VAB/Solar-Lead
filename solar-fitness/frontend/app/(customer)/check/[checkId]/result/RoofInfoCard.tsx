"use client";

import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { InfoTip } from "@/components/ui/InfoTip";
import { useT } from "@/lib/i18n/LanguageContext";
import { compassDirection, parseRoofSegments, type Assessment, type Site } from "@/lib/types";

// Total vs usable vs non-usable area — all three real: totalAreaM2 is
// engine/area.py::boundary_area_m2() (pre-setback/exclusion), usableAreaM2
// is what's left after AREA-02/03/04, and non-usable is simply their
// real difference — not a guess.
export function RoofInfoCard({
  assessment,
  site,
}: {
  assessment: Assessment;
  site: Pick<Site, "geometrySource" | "boundaryIsApproximate" | "geometryConfidence">;
}) {
  const { t } = useT();
  const total = assessment.totalAreaM2;
  const usable = assessment.usableAreaM2;
  const nonUsable = total != null && usable != null ? Math.max(0, total - usable) : null;
  const segments = parseRoofSegments(assessment.roofSegments);
  const usablePct = total != null && total > 0 && usable != null ? Math.min(100, (usable / total) * 100) : null;

  if (total == null && usable == null && segments.length === 0) return null;

  const hasSpace = usable != null && usable > 5;

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">🏠</span>
        <p className="text-sm font-semibold text-ink">{t("result.roofInfoTitle", "Your roof space")}</p>
      </div>
      <p className="mb-3 text-sm text-ink-soft">
        {usable == null
          ? t("result.roofInfoUnknown", "We're still working out how much space is on your roof.")
          : hasSpace
            ? t("result.roofInfoHasSpace", "You have space on your roof for solar panels.")
            : t("result.roofInfoNoSpace", "There isn't much clear space left on your roof for solar panels.")}
      </p>

      <div className="mb-3 flex items-baseline justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Roof information</p>
        {total != null && (
          <p className="text-xs text-ink-faint">
            Total <span className="font-medium tabular text-ink">{Math.round(total).toLocaleString()} m²</span>
          </p>
        )}
      </div>

      {usablePct != null && (
        <div className="mb-3" role="img" aria-label={`${Math.round(usablePct)}% of the roof is usable`}>
          <div className="flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-[var(--surface-2)]">
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{ width: `${usablePct}%`, background: "var(--good)" }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-start gap-2">
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--good)" }} aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-[11px] text-ink-faint">Usable area</p>
            <p className="mt-0.5 font-medium text-ink tabular">
              {usable != null ? `${Math.round(usable).toLocaleString()} m²` : "—"}
              {usablePct != null && <span className="ml-1 font-normal text-ink-faint">({Math.round(usablePct)}%)</span>}
            </p>
          </div>
        </div>
        <div className="flex items-start gap-2">
          <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: "var(--surface-2)", border: "1px solid var(--line)" }} aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-[11px] text-ink-faint">Non-usable area</p>
            <p className="mt-0.5 font-medium text-ink tabular">
              {nonUsable != null ? `${Math.round(nonUsable).toLocaleString()} m²` : "—"}
            </p>
          </div>
        </div>
      </div>

      {(site.geometryConfidence != null || segments.length > 0) && (
        <TechnicalDetails label="Roof measurement details">
          <p className="text-xs text-ink-faint">
            {site.geometrySource === "solar_api_mask" || site.geometrySource === "manual_polygon"
              ? "Boundary source: a traced roof outline"
              : site.geometrySource === "field_measured"
                ? "Boundary source: a field-measured survey"
                : "Boundary source: an approximate automatic outline"}
            {site.geometryConfidence != null && (
              <>
                {" · "}
                {Math.round(site.geometryConfidence * 100)}% boundary confidence
                <InfoTip>How closely the traced roof outline matches the real building shape.</InfoTip>
              </>
            )}
          </p>

          {segments.length > 0 && (
            <div className="mt-2.5 border-t border-line pt-2.5">
              <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
                Roof {segments.length > 1 ? "planes" : "orientation"}
              </p>
              <ul className="space-y-2">
                {segments.map((segment) => (
                  <li key={segment.segmentIndex} className="flex items-center justify-between text-sm">
                    <span className="text-ink-soft">
                      {segments.length > 1 ? `Section ${segment.segmentIndex + 1}` : "Your roof"}
                      {segment.azimuthDeg != null && ` — facing ${compassDirection(segment.azimuthDeg)}`}
                    </span>
                    <span className="font-medium text-ink">
                      {segment.pitchDeg != null ? `${segment.pitchDeg.toFixed(0)}° pitch` : "—"}
                      {segment.areaM2 != null && (
                        <span className="ml-1.5 font-normal text-ink-faint">· {segment.areaM2.toFixed(0)} m²</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </TechnicalDetails>
      )}
    </Card>
  );
}
