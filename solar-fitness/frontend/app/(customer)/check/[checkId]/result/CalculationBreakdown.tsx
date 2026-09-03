"use client";

// "How we calculated your recommendation" — CON-04's ceiling ledger, in
// language a homeowner can act on.
//
// Every number here was already computed and stored by the engine; the
// ledger was simply dropped on the way to the frontend, so a customer saw
// a kWp figure and a constraint NAME with nothing behind it. Nothing is
// recalculated in this component, and nothing is invented: an assessment
// that carries no ledger renders nothing at all.

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Assessment, CeilingLedgerEntry } from "@/lib/types";
import { formatKwp } from "@/lib/utils";

// Substation-level headroom. Real, and useful to a grid engineer, but
// meaningless to a homeowner — and a 2,000 kWp row beside a 4 kWp
// recommendation invites exactly the wrong conclusion.
const HIDDEN_FROM_HOMEOWNERS = new Set(["evacuation_headroom"]);

const CONSTRAINT_LABEL: Record<string, string> = {
  usable_area: "Space on your roof",
  consumption_offset: "Your electricity usage",
  net_metering_cap: "Net-metering limit",
  transformer_headroom: "Local transformer capacity",
  subsidy_tier_cap: "Subsidy category limit",
  evacuation_headroom: "Grid capacity",
};

/** Why the recommendation landed where it did, in one sentence. */
function bindingExplanation(binding: string | null, hasBill: boolean): string {
  switch (binding) {
    case "consumption_offset":
      return "Your recommendation is set by how much electricity you actually use — there's no benefit in generating far more than you consume.";
    case "usable_area":
      return hasBill
        ? "Your recommendation is set by the space available on your roof."
        : "Your recommendation is based on the space available on your roof. Tell us your electricity bill and we can size it to what you actually use.";
    case "net_metering_cap":
      return "Your recommendation is set by your DISCOM's net-metering limit for this connection.";
    case "transformer_headroom":
      return "Your recommendation is set by the spare capacity on your local transformer.";
    case "subsidy_tier_cap":
      return "Your recommendation is set by the cap on your subsidy category.";
    default:
      return "Your recommendation is the lowest of every limit we checked.";
  }
}

function statusNote(entry: CeilingLedgerEntry): string {
  if (entry.status === "insufficient_data") return "To be confirmed during the site survey";
  if (entry.status === "not_applicable") return "Doesn't apply to this property";
  // The engine's own reason string is already customer-readable for the
  // evaluated ones ("207.0 m2 usable area at 0.2 kWp/m2"). Raw internal
  // messages only ever appear on insufficient_data, handled above.
  return entry.note ?? "";
}

export function CalculationBreakdown({ assessment }: { assessment: Assessment }) {
  const [open, setOpen] = useState(false);

  const ledger = (assessment.ceilingLedger ?? []).filter(
    (entry) => !HIDDEN_FROM_HOMEOWNERS.has(entry.label)
  );
  const usableArea = assessment.usableAreaM2;
  const maxKwp = assessment.maxTechnicalKwp;
  const recommended = assessment.capacityKwp;
  const headroom = assessment.headroomKwp;
  const binding = assessment.bindingConstraint?.name ?? null;

  // An older assessment predating the ledger has nothing to explain.
  // Rendering an empty shell would be worse than rendering nothing.
  if (!usableArea && !maxKwp && ledger.length === 0) return null;

  const hasBill = ledger.some(
    (entry) => entry.label === "consumption_offset" && entry.status === "ok"
  );
  // Only worth mentioning when there is real room to grow.
  const showHeadroom = headroom != null && headroom > 0.5 && maxKwp != null;

  return (
    <div className="rounded-[var(--radius-app)] border border-line bg-surface p-4">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">
        How we calculated your recommendation
      </p>

      <p className="text-sm text-ink">
        {usableArea != null && maxKwp != null ? (
          <>
            Your roof has{" "}
            <span className="font-semibold">{Math.round(usableArea).toLocaleString()} m²</span> of
            usable space and can physically fit up to{" "}
            <span className="font-semibold">{formatKwp(maxKwp)}</span>.{" "}
          </>
        ) : null}
        {recommended > 0 && (
          <>
            We recommend <span className="font-semibold">{formatKwp(recommended)}</span>.
          </>
        )}
      </p>

      <p className="mt-1.5 text-sm text-ink-soft">{bindingExplanation(binding, hasBill)}</p>

      {showHeadroom && (
        <p className="mt-1.5 text-xs text-ink-faint">
          That leaves roughly {formatKwp(headroom!)} of unused roof capacity, so there&apos;s room
          to expand later if your usage grows.
        </p>
      )}

      {ledger.length > 0 && (
        <>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-3 flex items-center gap-1 text-xs font-medium text-blue hover:underline"
          >
            <ChevronDown
              size={13}
              strokeWidth={2}
              className={`transition-transform ${open ? "rotate-180" : ""}`}
              aria-hidden="true"
            />
            {open ? "Hide calculation details" : "View calculation details"}
          </button>

          {open && (
            <div className="mt-2.5 space-y-2 border-t border-line pt-2.5">
              <p className="text-xs text-ink-faint">
                We work out every limit that applies, then recommend the smallest.
              </p>
              {ledger.map((entry) => (
                <div
                  key={entry.label}
                  className="flex items-start justify-between gap-3 text-sm"
                >
                  <div className="min-w-0">
                    <p className="text-ink">
                      {CONSTRAINT_LABEL[entry.label] ?? entry.label}
                      {entry.isBinding && (
                        <span
                          className="ml-2 rounded-[3px] px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                          style={{ background: "var(--warn)", color: "#fff" }}
                        >
                          Deciding limit
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-faint">{statusNote(entry)}</p>
                  </div>
                  {/* Never 0 kWp for an unevaluated limit — that would
                      claim the opposite of "we haven't checked yet". */}
                  <span className="shrink-0 font-mono text-sm tabular-nums text-ink-soft">
                    {entry.kwp == null ? "—" : formatKwp(entry.kwp)}
                  </span>
                </div>
              ))}
              <p className="pt-1 text-[11px] text-ink-faint">
                Estimates use our standard assumptions for panel density and electricity tariff. A
                site survey confirms the final figures.
              </p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
