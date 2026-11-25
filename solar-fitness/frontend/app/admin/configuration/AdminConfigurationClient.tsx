"use client";

import { useState } from "react";
import {
  usePlatformHealth,
  useRotateApiKey,
  useFeatureFlags,
  useSetFeatureFlag,
  useServiceApiKeys,
  useFinancialConfig,
  useSetFinancialConfig,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { QuotaBar } from "@/components/admin/QuotaBar";
import { KeyRound } from "lucide-react";
import type { FinancialAssumptions, FinancialAssumptionsInput, SeasonCalendarMonths } from "@/lib/api/client";
import type { useSetFinancialConfig as UseSetFinancialConfig } from "@/lib/query/hooks";

// The only non-numeric field on the form besides `note` — excluded from
// field()'s generic key type below so `form[key]` always type-checks as
// a plain number/null, never this nested object.
type NumericAssumptionKey = Exclude<keyof FinancialAssumptionsInput, "note" | "seasonCalendarMonths">;

function parseMonthList(raw: string): number[] {
  return raw
    .split(",")
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isInteger(n) && n >= 1 && n <= 12);
}

// Keyed by `data.version` from the parent below, so a freshly-saved (or
// freshly-fetched) version mounts a brand-new editor with fresh local
// FORM state, instead of a useEffect resyncing state that's already
// mounted — an admin's in-progress edit is intentionally NOT preserved
// across a successful save, since the fields now reflect exactly what
// was just published as the new current version.
//
// `save` (the mutation) is passed in from the never-remounted parent
// rather than created here — creating it here would reset save.isSuccess
// back to false the instant the remount happens (right after a
// successful publish invalidates the query and bumps `data.version`),
// which silently ate the very "Saved." confirmation the mutation exists
// to show.
function FinancialConfigEditor({
  data,
  save,
}: {
  data: FinancialAssumptions;
  save: ReturnType<typeof UseSetFinancialConfig>;
}) {
  const [form, setForm] = useState<FinancialAssumptionsInput>({
    tariffEscalationPctPerYear: data.tariffEscalationPctPerYear,
    exportTariffInrPerKwh: data.exportTariffInrPerKwh,
    defaultSelfConsumptionRatio: data.defaultSelfConsumptionRatio,
    annualMaintenanceCostInrPerKwp: data.annualMaintenanceCostInrPerKwp,
    inverterReplacementYear: data.inverterReplacementYear,
    inverterReplacementCostInrPerKwp: data.inverterReplacementCostInrPerKwp,
    financingDefaultDownPaymentPct: data.financingDefaultDownPaymentPct,
    financingDefaultInterestRatePct: data.financingDefaultInterestRatePct,
    financingDefaultTenureYears: data.financingDefaultTenureYears,
    annualConsumptionGrowthPct: data.annualConsumptionGrowthPct,
    rainySeasonFactorPct: data.rainySeasonFactorPct,
    summerMonths: data.summerMonths,
    rainyMonths: data.rainyMonths,
    winterMonths: data.winterMonths,
    summerGenerationShare: data.summerGenerationShare,
    rainyGenerationShare: data.rainyGenerationShare,
    winterGenerationShare: data.winterGenerationShare,
    seasonCalendarMonths: data.seasonCalendarMonths,
    note: null,
  });
  const [note, setNote] = useState("");

  const monthTotal = form.summerMonths + form.rainyMonths + form.winterMonths;
  const shareTotal = form.summerGenerationShare + form.rainyGenerationShare + form.winterGenerationShare;

  const setCalendarMonths = (season: keyof SeasonCalendarMonths, raw: string) => {
    setForm({
      ...form,
      seasonCalendarMonths: { ...form.seasonCalendarMonths, [season]: parseMonthList(raw) },
    });
  };

  const field = (
    key: NumericAssumptionKey,
    label: string,
    opts: { step?: number; suffix?: string; optional?: boolean } = {}
  ) => (
    <label className="flex items-center justify-between gap-3 py-2">
      <span className="text-sm text-ink-soft">{label}</span>
      <span className="flex items-center gap-1.5">
        <input
          type="number"
          step={opts.step ?? 0.1}
          value={form[key] ?? ""}
          onChange={(e) => {
            const raw = e.target.value;
            setForm({
              ...form,
              [key]: raw === "" ? (opts.optional ? null : 0) : Number(raw),
            });
          }}
          className="w-28 rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1 text-right text-sm tabular text-ink"
        />
        {opts.suffix && <span className="text-xs text-ink-faint">{opts.suffix}</span>}
      </span>
    </label>
  );

  return (
    <div>
      <p className="mb-2 text-xs text-ink-faint">
        Version {data.version} — these values drive every new Solar Financial Analysis projection on the customer
        result page. Saving publishes a NEW version; past projections keep the assumptions they were actually
        computed with.
      </p>
      <div className="divide-y divide-line">
        {field("tariffEscalationPctPerYear", "Electricity tariff escalation", { suffix: "%/yr" })}
        {field("exportTariffInrPerKwh", "Grid export / feed-in rate", { suffix: "Rs/kWh" })}
        {field("defaultSelfConsumptionRatio", "Default self-consumption ratio", { step: 0.05, suffix: "0–1" })}
        {field("annualMaintenanceCostInrPerKwp", "Annual maintenance cost", { step: 10, suffix: "Rs/kWp/yr" })}
        {field("inverterReplacementYear", "Inverter replacement year", { step: 1, suffix: "yr (blank = never)", optional: true })}
        {field("inverterReplacementCostInrPerKwp", "Inverter replacement cost", { step: 100, suffix: "Rs/kWp", optional: true })}
        {field("financingDefaultDownPaymentPct", "Default down payment", { suffix: "%" })}
        {field("financingDefaultInterestRatePct", "Default loan interest rate", { suffix: "%/yr" })}
        {field("financingDefaultTenureYears", "Default loan tenure", { step: 1, suffix: "yrs" })}
      </div>

      <p className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Seasonal electricity model
      </p>
      <div className="divide-y divide-line">
        {field("annualConsumptionGrowthPct", "Annual consumption growth", { suffix: "%/yr" })}
        {field("rainySeasonFactorPct", "Rainy season factor", { suffix: "% of summer–winter gap" })}
        {field("summerMonths", "Summer months", { step: 1, suffix: "months" })}
        {field("rainyMonths", "Rainy months", { step: 1, suffix: "months" })}
        {field("winterMonths", "Winter months", { step: 1, suffix: "months" })}
      </div>
      <p className="mt-1 text-[11px]" style={monthTotal !== 12 ? { color: "var(--bad)" } : { color: "var(--ink-faint)" }}>
        Total: {monthTotal} / 12 months{monthTotal !== 12 ? " — must total 12 to save" : ""}
      </p>

      <p className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Seasonal generation (fallback, used when no real satellite data is available)
      </p>
      <div className="divide-y divide-line">
        {field("summerGenerationShare", "Summer share", { step: 0.01, suffix: "0–1" })}
        {field("rainyGenerationShare", "Rainy share", { step: 0.01, suffix: "0–1" })}
        {field("winterGenerationShare", "Winter share", { step: 0.01, suffix: "0–1" })}
      </div>
      <p className="mt-1 text-[11px]" style={Math.abs(shareTotal - 1) > 0.01 ? { color: "var(--bad)" } : { color: "var(--ink-faint)" }}>
        Total: {shareTotal.toFixed(2)} / 1.00{Math.abs(shareTotal - 1) > 0.01 ? " — must total 1.00 to save" : ""}
      </p>

      <p className="mb-1 mt-4 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        Calendar months per season (1=Jan…12=Dec, used when real satellite generation data is available)
      </p>
      <div className="space-y-2">
        {(["summer", "rainy", "winter"] as const).map((season) => (
          <label key={season} className="flex items-center justify-between gap-3 text-sm">
            <span className="capitalize text-ink-soft">{season}</span>
            <input
              type="text"
              defaultValue={form.seasonCalendarMonths[season].join(",")}
              onChange={(e) => setCalendarMonths(season, e.target.value)}
              placeholder="e.g. 3,4,5,6"
              className="w-40 rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1 text-right text-sm tabular text-ink"
            />
          </label>
        ))}
      </div>

      <label className="mt-3 block text-sm text-ink-soft">
        Reason for this change (optional)
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. tariff revised for FY27"
          className="mt-1 w-full rounded-[var(--radius-app)] border border-line bg-paper px-2.5 py-1.5 text-sm text-ink"
        />
      </label>
      <div className="mt-3 flex items-center gap-2">
        <Button
          onClick={() => save.mutate({ ...form, note: note || null }, { onSuccess: () => setNote("") })}
          disabled={save.isPending || monthTotal !== 12 || Math.abs(shareTotal - 1) > 0.01}
        >
          {save.isPending ? "Publishing…" : "Publish new version"}
        </Button>
        {save.isSuccess && <span className="text-xs" style={{ color: "var(--good)" }}>Saved.</span>}
        {save.isError && <span className="text-xs" style={{ color: "var(--bad)" }}>Could not save — try again.</span>}
      </div>
    </div>
  );
}

function FinancialConfigForm() {
  const config = useFinancialConfig();
  const save = useSetFinancialConfig();
  if (config.isLoading) return <CardSkeleton />;
  if (config.isError || !config.data) {
    return <ErrorState description="Could not load financial assumptions." onRetry={() => config.refetch()} />;
  }
  return <FinancialConfigEditor key={config.data.version} data={config.data} save={save} />;
}

export function AdminConfigurationClient() {
  const health = usePlatformHealth();
  const rotate = useRotateApiKey();
  const flags = useFeatureFlags();
  const setFlag = useSetFeatureFlag();
  const apiKeys = useServiceApiKeys();
  const [rotateTarget, setRotateTarget] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">Third-party API status</h2>
        {health.isLoading && <CardSkeleton />}
        {health.isError && <ErrorState description="Could not load platform health." onRetry={() => health.refetch()} />}
        {health.data && (
          <div className="space-y-3">
            {health.data.quotas.map((q) => (
              <QuotaBar key={q.service} quota={q} />
            ))}
          </div>
        )}
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">Feature flags</h2>
        {flags.isLoading && <CardSkeleton />}
        {flags.isError && <ErrorState description="Could not load feature flags." onRetry={() => flags.refetch()} />}
        {flags.data && (
          <ul className="divide-y divide-line">
            {flags.data.map((flag) => (
              <li key={flag.key} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium text-ink">{flag.label}</p>
                  <p className="text-xs text-ink-soft">{flag.description}</p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={flag.enabled}
                  disabled={setFlag.isPending}
                  onClick={() => setFlag.mutate({ key: flag.key, enabled: !flag.enabled })}
                  className="relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50"
                  style={{ background: flag.enabled ? "var(--brand)" : "var(--surface-2)" }}
                >
                  <span
                    className="absolute top-0.5 h-5 w-5 rounded-full bg-paper transition-transform"
                    style={{ transform: flag.enabled ? "translateX(22px)" : "translateX(2px)" }}
                  />
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Solar financial analysis assumptions
        </h2>
        <FinancialConfigForm />
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">API keys</h2>
        {apiKeys.isLoading && <CardSkeleton />}
        {apiKeys.isError && <ErrorState description="Could not load API keys." onRetry={() => apiKeys.refetch()} />}
        {apiKeys.data && (
          <ul className="divide-y divide-line">
            {apiKeys.data.map((k) => (
              <li key={k.service} className="flex items-center justify-between gap-3 py-3">
                <div>
                  <p className="text-sm font-medium text-ink">{k.service}</p>
                  <p className="font-mono tabular text-xs text-ink-faint">{k.maskedValue}</p>
                </div>
                <Button variant="secondary" size="sm" onClick={() => setRotateTarget(k.service)} disabled={rotate.isPending}>
                  <KeyRound size={13} strokeWidth={1.75} /> Rotate key
                </Button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={!!rotateTarget}
        title={rotateTarget ? `Rotate the ${rotateTarget} key?` : ""}
        description="The current key will be invalidated immediately. Any integration still using the old key will start failing until updated."
        confirmLabel="Rotate key"
        tone="danger"
        pending={rotate.isPending}
        onCancel={() => setRotateTarget(null)}
        onConfirm={() => rotateTarget && rotate.mutate(rotateTarget, { onSuccess: () => setRotateTarget(null) })}
      />
    </div>
  );
}
