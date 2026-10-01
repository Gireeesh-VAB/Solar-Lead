"use client";

// domain/assessment.py::ObstacleType — a fixed, real 7-value
// classification from the vision pipeline, each with a real detection
// confidence. Reuses useCheckObstacles' own query key, so this never
// issues a second network request beyond what ResultMap already fetches.

import Link from "next/link";
import { CircleHelp, Droplet, Fan, Flame, Plus, Radio, Wind, Zap } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { InfoTip } from "@/components/ui/InfoTip";
import { useCheckObstacles } from "@/lib/query/hooks";
import { useT } from "@/lib/i18n/LanguageContext";
import type { ObstacleType } from "@/lib/api/client";

/** Exported so the obstacle-marking screen uses literally the same icon
 *  and wording per type — a customer-marked water tank must be
 *  indistinguishable from a detected one, which it only is if there is
 *  one map, not two that drift apart. */
export const TYPE_META: Record<ObstacleType, { label: string; icon: typeof Droplet }> = {
  water_tank: { label: "Water tank", icon: Droplet },
  hvac_unit: { label: "HVAC unit", icon: Fan },
  chimney: { label: "Chimney", icon: Flame },
  existing_solar_panel: { label: "Existing solar panel", icon: Zap },
  vent: { label: "Vent", icon: Wind },
  antenna: { label: "Antenna", icon: Radio },
  other: { label: "Other structure", icon: CircleHelp },
};

export function ObstructionsList({ checkId }: { checkId: string }) {
  const { t } = useT();
  const { data } = useCheckObstacles(checkId);
  if (!data) return null;

  const count = data.obstacles.length;

  // Deliberately ONE list with one wording, whatever `source` each item
  // carries. A water tank the vision pipeline found and one the customer
  // pointed at are the same fact about the same roof, and the panel
  // layout avoids both identically — so provenance lives in the data,
  // never in the styling here.
  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">🚧</span>
        <p className="text-sm font-semibold text-ink">{t("result.obstructionsTitle", "What's on your roof")}</p>
      </div>
      <p className="mb-3 text-sm text-ink-soft">
        {count === 0
          ? data.detected
            ? t(
                "result.obstructionsNoneFound",
                "We didn't spot anything on your roof. If we've missed something, tell us."
              )
            : t(
                "result.obstructionsNotLookedYet",
                "We haven't been able to check your roof for water tanks, AC units and the like. You can tell us what's there."
              )
          : count === 1
            ? t(
                "result.obstructionsDescriptionOne",
                "There is {count} thing on your roof. We won't place solar panels there.",
                { count }
              )
            : t(
                "result.obstructionsDescriptionOther",
                "There are {count} things on your roof. We won't place solar panels there.",
                { count }
              )}
      </p>
      <ul className="space-y-2.5">
        {data.obstacles.map((obstacle) => {
          const meta = obstacle.type ? TYPE_META[obstacle.type] : null;
          const Icon = meta?.icon ?? CircleHelp;
          return (
            <li key={obstacle.id} className="flex items-center gap-2.5 text-sm">
              <span
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-app)]"
                style={{ background: "var(--surface-2)", color: "var(--amber)" }}
                aria-hidden="true"
              >
                <Icon size={14} strokeWidth={1.75} />
              </span>
              <span className="text-ink">{meta?.label ?? "Detected obstruction"}</span>
              {obstacle.confidence != null && (
                <span className="ml-auto flex items-center gap-1 text-xs text-ink-faint">
                  {Math.round(obstacle.confidence * 100)}% sure
                  <InfoTip>How confident we are that this is really here, based on the satellite photo.</InfoTip>
                </span>
              )}
            </li>
          );
        })}
      </ul>
      <Link
        href={`/check/${checkId}/obstacles`}
        className="mt-3 inline-flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-xs font-medium text-blue transition-colors hover:border-blue hover:bg-surface"
      >
        <Plus size={13} strokeWidth={1.75} aria-hidden="true" />
        {count === 0
          ? t("result.obstructionsMarkCta", "Tell us what's on your roof")
          : t("result.obstructionsMarkMoreCta", "Add something we missed")}
      </Link>
    </Card>
  );
}
