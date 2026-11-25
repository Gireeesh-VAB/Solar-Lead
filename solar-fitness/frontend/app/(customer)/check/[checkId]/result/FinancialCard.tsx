"use client";

// FIN-01 — engine/financials.py::estimate_financials()'s real output.
// An indicative ESTIMATE (config-pack cost/kWp, subsidy scheme,
// tariff) — never a real vendor quote. Renders nothing when the
// assessment carries no financialEstimate (older assessment, or no
// resolved capacity to cost out), same discipline as every other card
// on this page.

import { IndianRupee, TrendingDown } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import type { FinancialEstimate } from "@/lib/types";
import { formatInr } from "@/lib/utils";
import { useT } from "@/lib/i18n/LanguageContext";

const COST_LINE_ITEMS: { key: keyof FinancialEstimate; label: string }[] = [
  { key: "panelCostInr", label: "Panels" },
  { key: "inverterCostInr", label: "Inverter" },
  { key: "mountingStructureCostInr", label: "Mounting structure" },
  { key: "electricalMaterialCostInr", label: "Electrical material" },
  { key: "installationCostInr", label: "Installation labor" },
];

export function FinancialCard({ financials }: { financials: FinancialEstimate | null | undefined }) {
  const { t } = useT();
  if (!financials) return null;

  const hasSavings = financials.annualSavingsInr != null;

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">💰</span>
        <p className="text-sm font-semibold text-ink">{t("result.savingsTitle", "Your savings")}</p>
      </div>
      <p className="mb-3 text-sm text-ink-soft">
        {hasSavings
          ? t("result.savingsDescHasSavings", "Solar can lower your electricity bill and pay for itself over time.")
          : t(
              "result.savingsDescNoSavings",
              "Here's what solar could cost — savings depend on how much electricity you use."
            )}
      </p>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{ background: "var(--warn-bg)", color: "var(--amber)" }}
            aria-hidden="true"
          >
            <IndianRupee size={15} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold leading-tight tabular text-ink">
              {financials.customerContributionInr != null ? formatInr(financials.customerContributionInr) : "—"}
            </p>
            <p className="truncate text-[11px] text-ink-faint">Your contribution</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
          <span
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{ background: "var(--good-bg)", color: "var(--good)" }}
            aria-hidden="true"
          >
            <TrendingDown size={15} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <p className="text-base font-semibold leading-tight tabular text-ink">
              {financials.paybackPeriodYears != null ? `${financials.paybackPeriodYears.toFixed(1)} yrs` : "—"}
            </p>
            <p className="truncate text-[11px] text-ink-faint">Estimated payback</p>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-sm">
        <span className="text-ink-soft">Total project cost</span>
        <span className="font-medium tabular text-ink">
          {financials.totalProjectCostInr != null ? formatInr(financials.totalProjectCostInr) : "—"}
        </span>
      </div>
      {hasSavings && (
        <div className="mt-1 flex items-center justify-between text-sm">
          <span className="text-ink-soft">Estimated annual savings</span>
          <span className="font-medium tabular text-ink">{formatInr(financials.annualSavingsInr!)}</span>
        </div>
      )}

      <TechnicalDetails label="Cost breakdown">
        <div className="space-y-2">
          {COST_LINE_ITEMS.map(({ key, label }) => {
            const value = financials[key];
            return (
              <div key={key} className="flex items-center justify-between text-sm">
                <span className="text-ink-soft">{label}</span>
                <span className="font-mono tabular-nums text-ink-soft">
                  {typeof value === "number" ? formatInr(value) : "—"}
                </span>
              </div>
            );
          })}
          {financials.tenYearSavingsInr != null && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-soft">10-year savings</span>
              <span className="font-mono tabular-nums text-ink-soft">{formatInr(financials.tenYearSavingsInr)}</span>
            </div>
          )}
          {financials.twentyYearSavingsInr != null && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-ink-soft">20-year savings</span>
              <span className="font-mono tabular-nums text-ink-soft">{formatInr(financials.twentyYearSavingsInr)}</span>
            </div>
          )}
          <p className="pt-1 text-[11px] text-ink-faint">
            An indicative estimate based on standard cost and tariff assumptions, not a vendor quote — final pricing
            is confirmed during your site survey.
          </p>
        </div>
      </TechnicalDetails>
    </Card>
  );
}
