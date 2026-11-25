"use client";

// FIN-01 — engine/financials.py::estimate_financials()'s real subsidy
// output, plus its deterministic, template-generated explanation
// (_explain_subsidy(), never free-form/AI-written text). Three render
// states, all real, none fabricated:
//   - no data yet (no capacity resolved, or an older assessment
//     predating this field) -> a plain "can't be determined" message,
//     never a guessed number;
//   - not eligible -> a clear "Not Eligible" state with the real reason,
//     plus the scheme's maximum shown for context (never conflated with
//     "your amount");
//   - eligible -> the full System Cost / Maximum Subsidy / Eligible
//     Subsidy / Payable Amount breakdown, plus a collapsible
//     explanation of exactly how the eligible figure was reached.

import { IndianRupee, CheckCircle2, XCircle } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import type { FinancialEstimate } from "@/lib/types";
import { formatInr } from "@/lib/utils";

export function SubsidyBreakdownCard({
  financials,
  district,
  state,
}: {
  financials: FinancialEstimate | null | undefined;
  district?: string;
  state?: string;
}) {
  // Older assessments (or ones with no resolved capacity at all) carry
  // no financials, or financials without the subsidy explainability
  // fields — never invent a number for either case.
  if (!financials || financials.subsidySchemeMaxAmountInr == null) {
    return (
      <Card className="p-4">
        <div className="mb-1 flex items-center gap-1.5">
          <IndianRupee size={15} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />
          <p className="text-sm font-semibold text-ink">Government subsidy</p>
        </div>
        <p className="text-sm text-ink-soft">
          Subsidy cannot currently be determined yet — this result doesn&apos;t have a resolved system capacity to
          calculate it from.
        </p>
      </Card>
    );
  }

  const location = [district, state].filter(Boolean).join(", ");

  if (!financials.subsidyApplicable) {
    return (
      <Card className="p-4">
        <div className="mb-1 flex items-center gap-1.5">
          <IndianRupee size={15} strokeWidth={1.75} className="text-ink-soft" aria-hidden="true" />
          <p className="text-sm font-semibold text-ink">Government subsidy</p>
        </div>
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-ink-soft">Maximum government subsidy available</span>
          <span className="font-medium tabular text-ink">{formatInr(financials.subsidySchemeMaxAmountInr)}</span>
        </div>
        {financials.subsidySchemeName && (
          <p className="mt-0.5 text-[11px] text-ink-faint">{financials.subsidySchemeName}</p>
        )}
        <div className="mt-3 flex items-start gap-2 rounded-[var(--radius-app)] border border-line p-3" style={{ background: "var(--bad-bg)" }}>
          <XCircle size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color: "var(--bad)" }} aria-hidden="true" />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">Not Eligible</p>
            {financials.subsidyIneligibilityReason && (
              <p className="mt-0.5 text-sm text-ink-soft">{financials.subsidyIneligibilityReason}</p>
            )}
            {location && <p className="mt-1 text-[11px] text-ink-faint">Location: {location}</p>}
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="p-4">
      <div className="mb-1 flex items-center gap-1.5">
        <IndianRupee size={15} strokeWidth={1.75} style={{ color: "var(--good)" }} aria-hidden="true" />
        <p className="text-sm font-semibold text-ink">Government subsidy</p>
      </div>
      {financials.subsidySchemeName && <p className="mb-3 text-sm text-ink-soft">{financials.subsidySchemeName}</p>}

      <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)] p-2.5">
        <CheckCircle2 size={16} strokeWidth={1.75} style={{ color: "var(--good)" }} aria-hidden="true" />
        <span className="text-sm font-medium text-ink">Eligible</span>
      </div>

      <div className="mt-3 space-y-1.5">
        <div className="flex items-center justify-between text-sm">
          <span className="text-ink-soft">System cost</span>
          <span className="font-medium tabular text-ink">
            {financials.totalProjectCostInr != null ? formatInr(financials.totalProjectCostInr) : "—"}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-ink-soft">Maximum government subsidy</span>
          <span className="font-medium tabular text-ink">{formatInr(financials.subsidySchemeMaxAmountInr)}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-ink-soft">Your eligible subsidy</span>
          <span className="font-medium tabular" style={{ color: "var(--good)" }}>
            − {financials.subsidyAmountInr != null ? formatInr(financials.subsidyAmountInr) : "—"}
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between border-t border-line pt-1.5 text-sm">
          <span className="font-medium text-ink">You pay</span>
          <span className="font-semibold tabular text-ink">
            {financials.customerContributionInr != null ? formatInr(financials.customerContributionInr) : "—"}
          </span>
        </div>
      </div>

      <TechnicalDetails label="How this was calculated">
        <div className="space-y-2">
          {financials.subsidyExplanation.map((sentence) => (
            <p key={sentence} className="text-sm text-ink-soft">
              {sentence}
            </p>
          ))}
          {location && <p className="pt-1 text-[11px] text-ink-faint">Location: {location}</p>}
        </div>
      </TechnicalDetails>
    </Card>
  );
}
