"use client";

// FIN-02 — the Solar Financial Analysis / ROI section. Built entirely on
// top of the capacity/generation/cost figures the assessment already
// computed (see engine/financial_projection.py's own docstring) — never
// recomputes them.
//
// Kept deliberately short by default: a plain-language headline + 4
// numbers + a pay-upfront/finance toggle + ONE chart + the quote CTA are
// the only things visible without opening "See detailed numbers" —
// everything else (the other 3 charts, the 3-year and full year-by-year
// tables, the long-term timeline, the assumptions fine print) lives
// behind that one disclosure instead of being stacked inline, so this
// card doesn't turn the result page into a long scroll.
//
// Renders nothing when there's no projection yet — same discipline as
// every other card on this page.

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowRight, CalendarClock, PiggyBank, Wallet } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { InfoTip } from "@/components/ui/InfoTip";
import { useCheckFinancialProjection } from "@/lib/query/hooks";
import { useT } from "@/lib/i18n/LanguageContext";
import { formatInr, formatKwp, formatPercent } from "@/lib/utils";
import type {
  FinancialHorizonSummary,
  FinancialPayback,
  FinancialProjectionYear,
  SeasonalConsumption,
  SeasonalFinancial,
  SolarRequirement,
} from "@/lib/types";

const SEASON_META: Record<"summer" | "rainy" | "winter", { label: string; icon: string }> = {
  summer: { label: "Summer", icon: "☀️" },
  rainy: { label: "Rainy", icon: "🌧️" },
  winter: { label: "Winter", icon: "❄️" },
};
const SEASON_ORDER: ("summer" | "rainy" | "winter")[] = ["summer", "rainy", "winter"];

function compactInr(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 10_000_000) return `Rs ${(value / 10_000_000).toFixed(1)}Cr`;
  if (abs >= 100_000) return `Rs ${(value / 100_000).toFixed(1)}L`;
  if (abs >= 1000) return `Rs ${(value / 1000).toFixed(0)}K`;
  return formatInr(value);
}

function paybackLabel(payback: FinancialPayback): string {
  if (!payback.recovered || payback.paybackYears == null) return "Not within system lifetime";
  const years = Math.floor(payback.paybackYears);
  const months = Math.round(((payback.paybackYears % 1) * 12 + 12) % 12);
  if (years === 0) return `${months}mo`;
  if (months === 0) return `${years}yr`;
  return `${years}y ${months}m`;
}

function StatTile({
  icon: Icon,
  label,
  value,
  tone = "neutral",
}: {
  icon: typeof Wallet;
  label: string;
  value: string;
  tone?: "neutral" | "good";
}) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3 sm:flex-row sm:items-center sm:gap-2.5">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
        style={{
          background: tone === "good" ? "var(--good-bg)" : "var(--surface)",
          color: tone === "good" ? "var(--good)" : "var(--blue)",
        }}
        aria-hidden="true"
      >
        <Icon size={16} strokeWidth={1.75} />
      </span>
      <div className="min-w-0">
        <p className="text-lg font-semibold leading-tight tabular text-ink sm:truncate">{value}</p>
        <p className="text-[11px] text-ink-faint sm:truncate">{label}</p>
      </div>
    </div>
  );
}

const CHART_TOOLTIP_STYLE = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: "var(--radius-app)",
  fontSize: 12,
};

function CumulativeSavingsChart({
  yearly,
  investment,
  paybackYear,
}: {
  yearly: FinancialProjectionYear[];
  investment: number;
  paybackYear: number | null;
}) {
  const data = yearly.map((y) => ({ year: y.year, cumulative: Math.round(y.cumulativeSavingsInr) }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis dataKey="year" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--ink-faint)" }} />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={54}
          tick={{ fontSize: 11, fill: "var(--ink-faint)" }}
          tickFormatter={compactInr}
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [formatInr(Number(value)), "Cumulative savings"] as [string, string]}
          labelFormatter={(year) => `Year ${year}`}
        />
        <ReferenceLine
          y={investment}
          stroke="var(--ink-faint)"
          strokeDasharray="4 4"
          label={{ value: "Investment", position: "insideTopRight", fill: "var(--ink-faint)", fontSize: 11 }}
        />
        {paybackYear != null && (
          <ReferenceLine
            x={paybackYear}
            stroke="var(--amber)"
            strokeDasharray="3 3"
            label={{ value: "Payback", position: "top", fill: "var(--amber)", fontSize: 11 }}
          />
        )}
        <Area
          type="monotone"
          dataKey="cumulative"
          stroke="var(--brand)"
          strokeWidth={2}
          fill="var(--brand)"
          fillOpacity={0.1}
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function AnnualSavingsChart({ yearly }: { yearly: FinancialProjectionYear[] }) {
  const data = yearly.map((y) => ({ year: y.year, net: Math.round(y.netBenefitInr) }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis dataKey="year" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--ink-faint)" }} />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={54}
          tick={{ fontSize: 11, fill: "var(--ink-faint)" }}
          tickFormatter={compactInr}
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [formatInr(Number(value)), "Net annual benefit"] as [string, string]}
          labelFormatter={(year) => `Year ${year}`}
        />
        <Bar dataKey="net" fill="var(--brand)" maxBarSize={22} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function GenerationChart({ yearly }: { yearly: FinancialProjectionYear[] }) {
  const data = yearly.map((y) => ({ year: y.year, kwh: Math.round(y.generationKwh) }));
  return (
    <ResponsiveContainer width="100%" height={180}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis dataKey="year" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--ink-faint)" }} />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={54}
          domain={[0, "dataMax"]}
          tick={{ fontSize: 11, fill: "var(--ink-faint)" }}
          tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}K` : `${Math.round(v)}`)}
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value) => [`${Number(value).toLocaleString("en-IN")} kWh`, "Generation"] as [string, string]}
          labelFormatter={(year) => `Year ${year}`}
        />
        <Line type="monotone" dataKey="kwh" stroke="var(--blue)" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

// Indexed to Year 1 = 100 rather than a second y-axis — two measures of
// different units (Rs/kWh tariff vs Rs total savings) never share one
// axis; indexing to a common base shows the SAME relationship (does the
// tariff escalating outrun panel degradation) on one scale instead.
function TariffVsSavingsChart({ yearly }: { yearly: FinancialProjectionYear[] }) {
  const base = yearly[0];
  const data = yearly.map((y) => ({
    year: y.year,
    tariffIndex: base.tariffInrPerKwh > 0 ? Math.round((y.tariffInrPerKwh / base.tariffInrPerKwh) * 100) : 100,
    savingsIndex: base.grossBenefitInr > 0 ? Math.round((y.grossBenefitInr / base.grossBenefitInr) * 100) : 100,
  }));
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke="var(--line)" vertical={false} />
        <XAxis dataKey="year" tickLine={false} axisLine={false} tick={{ fontSize: 11, fill: "var(--ink-faint)" }} />
        <YAxis
          tickLine={false}
          axisLine={false}
          width={44}
          tick={{ fontSize: 11, fill: "var(--ink-faint)" }}
          tickFormatter={(v) => `${v}`}
        />
        <Tooltip
          contentStyle={CHART_TOOLTIP_STYLE}
          formatter={(value, name) => [`${value}`, String(name)] as [string, string]}
          labelFormatter={(year) => `Year ${year}`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="tariffIndex" name="Tariff (index)" stroke="var(--amber)" strokeWidth={2} dot={false} />
        <Line
          type="monotone"
          dataKey="savingsIndex"
          name="Savings (index)"
          stroke="var(--brand)"
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function ThreeYearTable({
  yearly,
  summary,
  investment,
}: {
  yearly: FinancialProjectionYear[];
  summary: FinancialHorizonSummary;
  investment: number;
}) {
  const rows = yearly.slice(0, 3);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-ink-faint">
            <th className="py-1.5 pr-2 font-medium">Year</th>
            <th className="py-1.5 pr-2 font-medium">Generation</th>
            <th className="py-1.5 pr-2 font-medium">Savings</th>
            <th className="py-1.5 pr-2 font-medium">Maintenance</th>
            <th className="py-1.5 pr-2 font-medium">Replacement</th>
            <th className="py-1.5 pr-2 font-medium">Net benefit</th>
            <th className="py-1.5 font-medium">Cumulative</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((y) => (
            <tr key={y.year} className="border-t border-line">
              <td className="py-1.5 pr-2 font-medium tabular text-ink">Y{y.year}</td>
              <td className="py-1.5 pr-2 tabular text-ink-soft">{Math.round(y.generationKwh).toLocaleString("en-IN")} kWh</td>
              <td className="py-1.5 pr-2 tabular text-ink-soft">{compactInr(y.grossBenefitInr)}</td>
              <td className="py-1.5 pr-2 tabular text-ink-soft">{compactInr(y.maintenanceCostInr)}</td>
              <td className="py-1.5 pr-2 tabular text-ink-soft">{y.otherCostInr > 0 ? compactInr(y.otherCostInr) : "—"}</td>
              <td className="py-1.5 pr-2 tabular text-ink">{compactInr(y.netBenefitInr)}</td>
              <td className="py-1.5 tabular text-ink">{compactInr(y.cumulativeSavingsInr)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t border-line font-semibold">
            <td className="py-1.5 pr-2 text-ink">Total</td>
            <td className="py-1.5 pr-2 tabular text-ink">{Math.round(summary.totalGenerationKwh).toLocaleString("en-IN")} kWh</td>
            <td className="py-1.5 pr-2 tabular text-ink">{compactInr(summary.totalGrossSavingsInr)}</td>
            <td className="py-1.5 pr-2 tabular text-ink" colSpan={2}>{compactInr(summary.totalCostsInr)}</td>
            <td className="py-1.5 pr-2 tabular text-ink">{compactInr(summary.totalNetSavingsInr)}</td>
            <td className="py-1.5 tabular text-ink">{compactInr(summary.totalNetSavingsInr)}</td>
          </tr>
        </tfoot>
      </table>
      <p className="mt-2 text-[11px] text-ink-faint">
        {summary.investmentRecovered
          ? `Your investment is fully recovered within 3 years — ${compactInr(summary.profitAfterRecoveryInr)} in profit already banked.`
          : `Not yet fully recovered after 3 years — ${compactInr(
              Math.max(0, investment - summary.totalNetSavingsInr)
            )} of your investment still outstanding.`}
      </p>
    </div>
  );
}

function LongTermTimeline({ horizons, investment }: { horizons: FinancialHorizonSummary[]; investment: number }) {
  return (
    <div className="-mx-1 flex snap-x gap-2 overflow-x-auto px-1 pb-1">
      {horizons.map((h) => (
        <div
          key={h.horizonYears}
          className="min-w-[9.5rem] shrink-0 snap-start rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3"
        >
          <p className="text-xs font-semibold text-ink">After Year {h.horizonYears}</p>
          <p className="mt-1 text-sm font-semibold tabular text-ink">
            {h.investmentRecovered ? `+${compactInr(h.profitAfterRecoveryInr)} profit` : `${compactInr(h.totalNetSavingsInr)} saved`}
          </p>
          <p className="mt-0.5 text-[11px] text-ink-faint">
            {h.investmentRecovered ? "Investment recovered" : `${compactInr(Math.max(0, investment - h.totalNetSavingsInr))} left to recover`}
          </p>
          <p className="mt-1 text-[11px] font-medium" style={{ color: h.cumulativeRoiPct >= 0 ? "var(--good)" : "var(--ink-faint)" }}>
            ROI {formatPercent(h.cumulativeRoiPct, 0)}
          </p>
        </div>
      ))}
    </div>
  );
}

// FIN-03 §5/§26 — "Your electricity profile" + seasonal estimate. Never
// presents the rainy figure as measured — each tile says so directly.
function ElectricityProfileCard({ profile }: { profile: SeasonalConsumption }) {
  return (
    <div className="mt-3 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-ink-soft">Your electricity profile</span>
        <span className="text-ink-faint">
          Avg {Math.round(profile.averageMonthlyKwh).toLocaleString("en-IN")} kWh/mo
        </span>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2">
        {SEASON_ORDER.map((season) => {
          const meta = SEASON_META[season];
          const s = profile.seasons[season];
          return (
            <div key={season} className="rounded-[var(--radius-app)] border border-line bg-surface p-2 text-center">
              <p className="text-sm" aria-hidden="true">{meta.icon}</p>
              <p className="text-[11px] font-medium text-ink-soft">{meta.label}</p>
              <p className="text-sm font-semibold tabular text-ink">{Math.round(s.monthlyKwh)} kWh</p>
              {s.estimated && <p className="text-[10px] text-ink-faint">estimated</p>}
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-ink-faint">{profile.basis}</p>
    </div>
  );
}

// FIN-03 §6/§7/§8 — electricity requirement vs. what the roof can
// physically hold. recommendedKwp is always the smaller of the two, so
// this can never suggest more than the roof supports.
function SolarRequirementRow({ requirement }: { requirement: SolarRequirement }) {
  return (
    <div className="mt-2 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-ink-soft">Electricity requirement</span>
        <span className="font-medium tabular text-ink">{requirement.electricityRequiredKwp.toFixed(1)} kW</span>
      </div>
      <div className="mt-1 flex items-center justify-between">
        <span className="text-ink-soft">Your roof supports</span>
        <span className="font-medium tabular text-ink">{requirement.roofCapacityKwp.toFixed(1)} kW</span>
      </div>
      <div className="mt-1 flex items-center justify-between border-t border-line pt-1">
        <span className="font-medium text-ink">Recommended system</span>
        <span className="font-semibold tabular" style={{ color: "var(--good)" }}>
          {requirement.recommendedKwp.toFixed(1)} kW
        </span>
      </div>
      <p className="mt-1.5 text-[11px] text-ink-faint">
        {requirement.electricityRequiredKwp > requirement.roofCapacityKwp
          ? `Your roof can't fully cover your electricity needs, but it can still generate around ${requirement.coveragePct.toFixed(0)}% of what you use.`
          : `This system is expected to cover about ${requirement.coveragePct.toFixed(0)}% of your estimated electricity use.`}
      </p>
    </div>
  );
}

// FIN-03 §9/§10/§12 — the season-wise companion to the year-by-year
// chart, same underlying assumptions engine, just a different slice.
function SeasonalBreakdown({ seasonal, financedView }: { seasonal: SeasonalFinancial; financedView: boolean }) {
  return (
    <div className="space-y-2">
      {SEASON_ORDER.map((season) => {
        const meta = SEASON_META[season];
        const s = seasonal.seasons[season];
        const netBenefit = financedView ? s.netBenefitAfterEmiInr : s.netBenefitInr;
        return (
          <div key={season} className="rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-1.5 text-sm font-semibold text-ink">
                <span aria-hidden="true">{meta.icon}</span> {meta.label}
              </span>
              <span className="text-[11px] text-ink-faint">{s.months} months</span>
            </div>
            <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
              <span className="text-ink-soft">Consumption</span>
              <span className="text-right tabular text-ink">
                {Math.round(s.consumptionKwh).toLocaleString("en-IN")} kWh
              </span>
              <span className="text-ink-soft">Solar generation</span>
              <span className="text-right tabular text-ink">
                {Math.round(s.generationKwh).toLocaleString("en-IN")} kWh
              </span>
              <span className="text-ink-soft">Savings</span>
              <span className="text-right tabular text-ink">{compactInr(s.grossBenefitInr)}</span>
              <span className="text-ink-soft">{financedView ? "Costs + EMI" : "Costs"}</span>
              <span className="text-right tabular text-ink">
                {compactInr(financedView ? s.maintenanceCostInr + s.emiCostInr : s.maintenanceCostInr)}
              </span>
              <span className="font-medium text-ink">Net benefit</span>
              <span className="text-right font-semibold tabular" style={{ color: netBenefit >= 0 ? "var(--good)" : "var(--bad)" }}>
                {compactInr(netBenefit)}
              </span>
            </div>
          </div>
        );
      })}
      <div className="rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
        <div className="flex items-center justify-between text-sm">
          <span className="font-semibold text-ink">Annual total</span>
          <span
            className="font-semibold tabular"
            style={{
              color:
                (financedView ? seasonal.annualNetBenefitAfterEmiInr : seasonal.annualNetBenefitInr) >= 0
                  ? "var(--good)"
                  : "var(--bad)",
            }}
          >
            {compactInr(financedView ? seasonal.annualNetBenefitAfterEmiInr : seasonal.annualNetBenefitInr)}
          </span>
        </div>
        <p className="mt-1 text-[11px] text-ink-faint">
          {seasonal.generationShareSource === "pvgis_actual"
            ? "Seasonal generation split from your roof's own real satellite generation data."
            : "Seasonal generation split from configured seasonal estimates (no real satellite breakdown available)."}
        </p>
      </div>
    </div>
  );
}

export function FinancialAnalysisSection({
  checkId,
  eligibleForEnquiry = false,
}: {
  checkId: string;
  eligibleForEnquiry?: boolean;
}) {
  const { t } = useT();
  const [financedView, setFinancedView] = useState(false);
  const [viewMode, setViewMode] = useState<"year" | "season">("year");
  const { data } = useCheckFinancialProjection(checkId);

  const activeYearly = useMemo(() => {
    if (!data) return null;
    return financedView && data.financing ? data.financing.yearly : data.yearly;
  }, [data, financedView]);

  if (!data || !activeYearly) return null;

  const activePayback = financedView && data.financing ? data.financing.payback : data.payback;
  const activeInvestment = financedView && data.financing ? data.financing.downPaymentInr : data.initialInvestmentInr;
  const activeHorizons = financedView && data.financing ? data.financing.horizons : data.horizons;
  const activeThreeYearSummary =
    (financedView && data.financing ? data.financing.horizons : data.horizons).find((h) => h.horizonYears === 3) ??
    data.threeYearSummary;
  const lastHorizon = data.horizons[data.horizons.length - 1];

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">📈</span>
        <p className="text-sm font-semibold text-ink">
          {t("result.financialProjectionTitle", "Your solar financial analysis")}
        </p>
      </div>

      {/* FIN-03 — your reported usage, seasonalized, then compared
          against what the roof can actually hold. Renders nothing when
          there's no consumption estimate on file at all. */}
      {data.electricityProfile && <ElectricityProfileCard profile={data.electricityProfile} />}
      {data.solarRequirement && <SolarRequirementRow requirement={data.solarRequirement} />}

      {/* One plain sentence — the single thing a non-technical reader
          needs before anything else. */}
      <p className="mb-3 text-sm text-ink-soft">
        {lastHorizon?.investmentRecovered
          ? `Your ${formatKwp(data.capacityKwp)} system pays for itself in about ${paybackLabel(data.payback)}, then keeps saving you money for the rest of its ${data.systemLifetimeYears}-year life.`
          : `Your ${formatKwp(data.capacityKwp)} system could save you ${compactInr(lastHorizon?.totalNetSavingsInr ?? 0)} over its ${data.systemLifetimeYears}-year life.`}
      </p>

      {/* The 4 numbers that actually matter for a decision. */}
      <div className="grid grid-cols-2 gap-2.5">
        <StatTile icon={Wallet} label={financedView ? "Your down payment" : "Your investment"} value={compactInr(activeInvestment)} />
        <StatTile icon={CalendarClock} label="Payback period" value={paybackLabel(activePayback)} />
        <StatTile icon={PiggyBank} label="Annual savings" value={compactInr(data.yearly[0].grossBenefitInr)} tone="good" />
        <StatTile
          icon={PiggyBank}
          label={`${lastHorizon?.horizonYears ?? data.systemLifetimeYears}-year savings`}
          value={compactInr(lastHorizon?.totalNetSavingsInr ?? 0)}
          tone="good"
        />
      </div>

      {/* Ongoing costs — always visible, not buried in the disclosure:
          these already reduce every number above, so the customer should
          be able to see what's being subtracted without digging. */}
      <p className="mt-2 text-[11px] text-ink-faint">
        Already accounted for: ~{compactInr(data.yearly[0].maintenanceCostInr)}/yr maintenance
        {(() => {
          const replacement = data.yearly.find((y) => y.otherCostInr > 0);
          return replacement
            ? `, and a one-time ~${compactInr(replacement.otherCostInr)} component replacement (e.g. inverter) assumed around Year ${replacement.year}`
            : "";
        })()}
        .
      </p>

      {/* Year-wise / Season-wise — both use the SAME underlying figures,
          just a different slice (spec §9/§23: never a second engine). */}
      {data.seasonal && (
        <div className="mt-3 flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-1 text-xs">
          <button
            type="button"
            onClick={() => setViewMode("year")}
            className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
            style={viewMode === "year" ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
          >
            Yearly view
          </button>
          <button
            type="button"
            onClick={() => setViewMode("season")}
            className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
            style={viewMode === "season" ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
          >
            Seasonal view
          </button>
        </div>
      )}

      {/* Pay upfront / Finance it — a simple, familiar binary choice. */}
      {data.financing && (
        <div className="mt-3 flex items-center gap-1.5 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-1 text-xs">
          <button
            type="button"
            onClick={() => setFinancedView(false)}
            className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
            style={!financedView ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
          >
            Pay upfront
          </button>
          <button
            type="button"
            onClick={() => setFinancedView(true)}
            className="flex-1 rounded-[calc(var(--radius-app)-4px)] py-1.5 font-medium transition-colors"
            style={financedView ? { background: "var(--surface)", color: "var(--ink)" } : { color: "var(--ink-faint)" }}
          >
            Finance it
          </button>
        </div>
      )}
      {financedView && data.financing && (
        <p className="mt-2 text-xs text-ink-soft">
          Down payment {formatInr(data.financing.downPaymentInr)} + loan {formatInr(data.financing.loanAmountInr)} at{" "}
          {data.financing.interestRatePct}% for {data.financing.tenureYears} yrs — EMI ≈{" "}
          {formatInr(data.financing.monthlyEmiInr)}/mo.
        </p>
      )}

      {viewMode === "year" || !data.seasonal ? (
        /* The one chart that answers "will I make my money back, and
           when" — every other chart lives behind the disclosure below. */
        <div className="mt-4">
          <p className="mb-1 text-xs font-semibold text-ink-soft">When do you break even?</p>
          <CumulativeSavingsChart yearly={activeYearly} investment={activeInvestment} paybackYear={activePayback.paybackYear} />
        </div>
      ) : (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-semibold text-ink-soft">Season by season</p>
          <SeasonalBreakdown seasonal={data.seasonal} financedView={financedView} />
        </div>
      )}

      {eligibleForEnquiry && (
        <Link
          href={`/check/${checkId}/enquiry`}
          className="mt-3 flex items-center justify-center gap-1.5 rounded-[var(--radius-app)] bg-brand px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-brand-soft"
        >
          {t("result.financialProjectionCta", "Get your solar quote")}
          <ArrowRight size={15} strokeWidth={1.75} aria-hidden="true" />
        </Link>
      )}

      {/* Everything technical, in one place, closed by default. */}
      <TechnicalDetails label="See detailed year-by-year numbers" className="mt-4">
        <div className="space-y-4">
          <div>
            <p className="mb-1 text-xs font-semibold text-ink-soft">3-year detail</p>
            <ThreeYearTable yearly={activeYearly} summary={activeThreeYearSummary} investment={activeInvestment} />
          </div>

          <div>
            <p className="mb-1.5 text-xs font-semibold text-ink-soft">Long-term outlook</p>
            <LongTermTimeline horizons={activeHorizons} investment={activeInvestment} />
          </div>

          <div>
            <p className="mb-1 text-xs font-semibold text-ink-soft">Annual savings</p>
            <AnnualSavingsChart yearly={activeYearly} />
          </div>
          <div>
            <p className="mb-1 text-xs font-semibold text-ink-soft">Solar generation over time</p>
            <GenerationChart yearly={activeYearly} />
          </div>
          <div>
            <div className="mb-1 flex items-center gap-1">
              <p className="text-xs font-semibold text-ink-soft">Tariff escalation vs. your savings</p>
              <InfoTip>Both lines are indexed to Year 1 = 100, since tariff (Rs/unit) and savings (Rs) are different units.</InfoTip>
            </div>
            <TariffVsSavingsChart yearly={activeYearly} />
          </div>

          <div>
            <p className="mb-1 text-xs font-semibold text-ink-soft">Full year-by-year table</p>
            <div className="max-h-64 overflow-auto">
              <table className="w-full min-w-[480px] text-xs">
                <thead className="sticky top-0 bg-surface">
                  <tr className="text-left text-ink-faint">
                    <th className="py-1 pr-2 font-medium">Year</th>
                    <th className="py-1 pr-2 font-medium">Generation</th>
                    <th className="py-1 pr-2 font-medium">Tariff</th>
                    <th className="py-1 pr-2 font-medium">Maintenance</th>
                    <th className="py-1 pr-2 font-medium">Replacement</th>
                    <th className="py-1 pr-2 font-medium">Net benefit</th>
                    <th className="py-1 font-medium">Cumulative</th>
                  </tr>
                </thead>
                <tbody>
                  {activeYearly.map((y) => (
                    <tr
                      key={y.year}
                      className="border-t border-line"
                      style={y.otherCostInr > 0 ? { background: "var(--warn-bg)" } : undefined}
                    >
                      <td className="py-1 pr-2 tabular text-ink">Y{y.year}</td>
                      <td className="py-1 pr-2 tabular text-ink-soft">{Math.round(y.generationKwh).toLocaleString("en-IN")}</td>
                      <td className="py-1 pr-2 tabular text-ink-soft">Rs {y.tariffInrPerKwh.toFixed(2)}</td>
                      <td className="py-1 pr-2 tabular text-ink-soft">{compactInr(y.maintenanceCostInr)}</td>
                      <td className="py-1 pr-2 tabular text-ink-soft">
                        {y.otherCostInr > 0 ? compactInr(y.otherCostInr) : "—"}
                      </td>
                      <td className="py-1 pr-2 tabular text-ink-soft">{compactInr(y.netBenefitInr)}</td>
                      <td className="py-1 tabular text-ink-soft">{compactInr(y.cumulativeSavingsInr)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {activeYearly.some((y) => y.otherCostInr > 0) && (
              <p className="mt-1.5 text-[11px] text-ink-faint">
                Highlighted row: the year a component replacement (e.g. the inverter) is assumed — a one-time cost
                that year, which is why net benefit dips there before returning to its usual trend.
              </p>
            )}
          </div>

          <div className="rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
            <p className="text-xs font-semibold text-ink-soft">Lifetime costs</p>
            <div className="mt-1.5 flex items-center justify-between text-sm">
              <span className="text-ink-soft">Total maintenance ({activeYearly.length} yrs)</span>
              <span className="font-medium tabular text-ink">
                {compactInr(activeYearly.reduce((sum, y) => sum + y.maintenanceCostInr, 0))}
              </span>
            </div>
            <div className="mt-1 flex items-center justify-between text-sm">
              <span className="text-ink-soft">Total component replacement</span>
              <span className="font-medium tabular text-ink">
                {compactInr(activeYearly.reduce((sum, y) => sum + y.otherCostInr, 0))}
              </span>
            </div>
          </div>

          <div className="rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-3">
            <p className="text-xs font-semibold text-ink-soft">Assumptions</p>
            <p className="mt-1 text-[11px] text-ink-faint">{data.methodNotes}</p>
            <p className="mt-1.5 text-[11px] text-ink-faint">
              These figures are estimates based on the assumptions shown above. Actual savings may vary depending on
              electricity consumption, tariff changes, weather, system performance, maintenance, and applicable
              regulations.
            </p>
          </div>
        </div>
      </TechnicalDetails>
    </Card>
  );
}
