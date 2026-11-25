"use client";

import { AlertOctagon, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Badge, Card } from "@/components/ui/Primitives";
import type { Assessment } from "@/lib/types";
import { CONDITION_LABEL, CONDITION_SEVERITY, humanizeLabel, severityTone, type Severity } from "@/lib/simpleLanguage";
import { cn } from "@/lib/utils";
import { useT } from "@/lib/i18n/LanguageContext";

// StatusTone ("good"/"check"/"bad") -> this card's own red/amber/neutral
// badge tone + icon, via severityTone()'s 3-way collapse of the 4-tier
// severity above — kept local since Badge's tone prop uses different
// names than SimpleStatus's.
const TONE_STYLE: Record<"good" | "check" | "bad", { tone: "red" | "amber" | "neutral"; Icon: typeof AlertOctagon }> = {
  bad: { tone: "red", Icon: AlertOctagon },
  check: { tone: "amber", Icon: AlertTriangle },
  good: { tone: "neutral", Icon: CheckCircle2 },
};

interface RiskItem {
  title: string;
  detail: string;
  severity: Severity;
}

function buildRisks(assessment: Assessment): RiskItem[] {
  const risks: RiskItem[] = [];

  for (const condition of assessment.conditions ?? []) {
    risks.push({
      title: CONDITION_LABEL[condition.code] ?? condition.code,
      detail: condition.message,
      severity: CONDITION_SEVERITY[condition.code] ?? "Medium",
    });
  }

  for (const entry of assessment.ceilingLedger ?? []) {
    if (entry.status !== "insufficient_data") continue;
    risks.push({
      title: `${humanizeLabel(entry.label)} could not be evaluated`,
      detail: entry.isBinding
        ? "This is the constraint currently deciding your capacity — confirming it during a site survey may change your recommendation."
        : entry.note || "To be confirmed during the site survey.",
      severity: entry.isBinding ? "High" : "Low",
    });
  }

  // Highest severity first.
  const order: Severity[] = ["Critical", "High", "Medium", "Low"];
  return risks.sort((a, b) => order.indexOf(a.severity) - order.indexOf(b.severity));
}

export function RiskList({ assessment }: { assessment: Assessment }) {
  const { t } = useT();
  const risks = buildRisks(assessment);
  if (risks.length === 0) return null;

  return (
    <Card className="p-4">
      <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        {t("result.risksTitle", "Things to check")}
      </p>
      <ul className="space-y-3">
        {risks.map((risk, i) => {
          const { tone, Icon } = TONE_STYLE[severityTone(risk.severity)];
          return (
            <li key={i} className="flex items-start gap-2.5">
              <span
                className={cn(
                  "mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-[var(--radius-app)]",
                  tone === "red" ? "bg-[var(--bad-bg)] text-[var(--bad)]" : tone === "amber" ? "bg-[var(--warn-bg)] text-[var(--warn)]" : "bg-surface-2 text-ink-soft"
                )}
                aria-hidden="true"
              >
                <Icon size={13} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-medium text-ink">{risk.title}</span>
                  <Badge tone={tone === "red" ? "red" : tone === "amber" ? "amber" : "neutral"}>
                    {risk.severity}
                  </Badge>
                </div>
                <p className="mt-0.5 text-sm text-ink-soft">{risk.detail}</p>
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
