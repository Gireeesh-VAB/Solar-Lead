"use client";

import { Sun, Zap } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { SimpleStatus } from "@/components/ui/SimpleStatus";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { sunlightTier, shadeTier } from "@/lib/simpleLanguage";
import { useT } from "@/lib/i18n/LanguageContext";
import type { Assessment, Site } from "@/lib/types";

function PercentBar({ label, percent }: { label: string; percent: number | null }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-ink-soft">{label}</span>
        <span className="font-medium tabular text-ink">{percent != null ? `${Math.round(percent)}%` : "Not available"}</span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-2)]">
        {percent != null && (
          <div className="h-full rounded-full bg-blue transition-[width] duration-500" style={{ width: `${percent}%` }} />
        )}
      </div>
    </div>
  );
}

function panelLayoutSummary(panelLayout: Assessment["panelLayout"]): { panelCount: number; totalKwp: number } | null {
  if (!panelLayout || typeof panelLayout !== "object") return null;
  const status = (panelLayout as Record<string, unknown>).status;
  if (status !== "ok") return null;
  const panelCount = (panelLayout as Record<string, unknown>).panelCount;
  const totalKwp = (panelLayout as Record<string, unknown>).totalKwp;
  if (typeof panelCount !== "number" || typeof totalKwp !== "number") return null;
  return { panelCount, totalKwp };
}

// engine/generation.py::estimate_generation_kwh()'s real output, plus
// domain/site.py::ShadingEstimate — no monthly/peak/loss-breakdown
// figures exist anywhere in the engine, so none are shown here. p50/p90
// are always null today (GEN-06, deferred) — rendered as "not available
// yet", never estimated on the frontend.
export function SolarPotentialCard({
  assessment,
  site,
}: {
  assessment: Assessment;
  site: Pick<Site, "shadingScore" | "sunshineHoursPerYear" | "shadingSource">;
}) {
  const { t } = useT();
  const generation = assessment.generation;
  const layout = panelLayoutSummary(assessment.panelLayout);
  const shadingAvailable = site.shadingSource && site.shadingSource !== "unavailable";

  if (!generation && !layout && !shadingAvailable) return null;

  const sunExposurePct = shadingAvailable && site.shadingScore != null ? site.shadingScore * 100 : null;
  const performanceRatioPct = generation?.performanceRatio != null ? generation.performanceRatio * 100 : null;
  const sun = sunlightTier(shadingAvailable ? site.shadingScore : null);
  const shade = shadeTier(shadingAvailable ? site.shadingScore : null);

  const TIER_KEY: Record<string, string> = {
    Excellent: "result.tierExcellent",
    Good: "result.tierGood",
    Average: "result.tierAverage",
    Low: "result.tierLow",
    Medium: "result.tierMedium",
    High: "result.tierHigh",
    "Not available": "result.tierNotAvailable",
  };
  const sunLabel = t(TIER_KEY[sun.label], sun.label);
  const shadeLabel = t(TIER_KEY[shade.label], shade.label);

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">☀️</span>
        <p className="text-sm font-semibold text-ink">{t("result.sunlightTitle", "Sunlight & shade")}</p>
      </div>

      {shadingAvailable && (
        <>
          <SimpleStatus
            tone={sun.rating >= 4 ? "good" : sun.rating >= 3 ? "check" : "bad"}
            headline={
              sun.label === "Not available"
                ? t("result.sunlightNotAvailable", "Sunlight not available")
                : `${sunLabel} ${t("result.sunlightSuffix", "sunlight")}`
            }
            description={
              sun.rating >= 4
                ? t("result.sunlightDescGood", "Your roof gets plenty of sunlight.")
                : sun.rating === 3
                  ? t("result.sunlightDescFair", "Your roof gets a fair amount of sunlight.")
                  : t("result.sunlightDescLimited", "Your roof gets limited sunlight.")
            }
            sunRating={sun.rating}
          />
          <p className="mt-2 flex items-center gap-1.5 text-sm text-ink-soft">
            🌳 <span className="font-medium text-ink">{shadeLabel} {t("result.shadeSuffix", "shade")}</span>
            {shade.label === "Low" && t("result.shadeNoteLow", "— less shade means more solar power.")}
            {shade.label === "Medium" && t("result.shadeNoteMedium", "— some shade may reduce your solar power a little.")}
            {shade.label === "High" && t("result.shadeNoteHigh", "— shade is likely reducing your solar power.")}
          </p>
        </>
      )}

      {(layout || generation?.estimatedKwhPerYear != null) && (
        <div className="mt-4 grid grid-cols-2 gap-3">
          {layout && (
            <div className="flex items-center gap-2.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--warn-bg)", color: "var(--amber)" }}
                aria-hidden="true"
              >
                <Zap size={15} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <p className="text-base font-semibold leading-tight tabular text-ink">{layout.totalKwp.toFixed(1)} kW</p>
                <p className="truncate text-[11px] text-ink-faint">{layout.panelCount} panels</p>
              </div>
            </div>
          )}
          {generation?.estimatedKwhPerYear != null && (
            <div className="flex items-center gap-2.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--good-bg)", color: "var(--good)" }}
                aria-hidden="true"
              >
                <Sun size={15} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <p className="text-base font-semibold leading-tight tabular text-ink">
                  {Math.round(generation.estimatedKwhPerYear).toLocaleString()}
                </p>
                <p className="truncate text-[11px] text-ink-faint">kWh / year</p>
              </div>
            </div>
          )}
        </div>
      )}

      <TechnicalDetails label="Sunlight &amp; generation details">
        <div className="space-y-3">
          <PercentBar label="Sun exposure (unobstructed)" percent={sunExposurePct} />
          {performanceRatioPct != null && <PercentBar label="Performance ratio" percent={performanceRatioPct} />}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 border-t border-line pt-3">
          <div>
            <p className="text-[11px] text-ink-faint">Annual sunshine</p>
            <p className="mt-0.5 font-medium text-ink tabular">
              {shadingAvailable && site.sunshineHoursPerYear != null
                ? `${Math.round(site.sunshineHoursPerYear).toLocaleString()} hrs/yr`
                : "Not available"}
            </p>
          </div>
          {generation?.pvgisAnnualKwh != null && (
            <div>
              <p className="text-[11px] text-ink-faint">Independent cross-check (PVGIS)</p>
              <p className="mt-0.5 font-medium text-ink tabular">
                {Math.round(generation.pvgisAnnualKwh).toLocaleString()} kWh
              </p>
            </div>
          )}
        </div>

        {generation?.specificYieldKwhPerKwp != null && (
          <p className="mt-3 text-xs text-ink-faint">
            Specific yield: {generation.specificYieldKwhPerKwp.toFixed(0)} kWh/kWp/yr
            {generation.method && ` · ${generation.method === "weather_refined" ? "weather-refined estimate" : "standard estimate"}`}
          </p>
        )}
        <p className="mt-1 text-xs text-ink-faint">
          Monthly/peak generation breakdown not available yet — this figure is annual only.
        </p>
      </TechnicalDetails>
    </Card>
  );
}
