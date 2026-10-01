import { Check, X } from "lucide-react";
import { Card } from "@/components/ui/Primitives";
import { SimpleStatus } from "@/components/ui/SimpleStatus";
import type { ElectricalReadiness } from "@/lib/types";

// routers/app_sites.py::ElectricalReadinessOut — a customer-safe subset
// of the vendor's real, submitted ElectricalAssessment (captured only
// during an in-person site survey, app_vendor.py). site.electricalReadiness
// is null until a vendor has actually submitted one for this site's
// survey job — before that, this card only says "confirmed during your
// survey", never a guessed checklist.
const CHECKLIST: { key: keyof ElectricalReadiness; label: string }[] = [
  { key: "meterAvailable", label: "Electricity meter" },
  { key: "panelChecked", label: "Electrical panel (distribution board)" },
  { key: "earthingAvailable", label: "Earthing" },
  { key: "inverterLocationAvailable", label: "Space for the inverter" },
  { key: "cableRouteAvailable", label: "Cable route" },
];

export function ElectricalSafetyCard({
  electricalReadiness,
}: {
  electricalReadiness: ElectricalReadiness | null | undefined;
}) {
  const recorded = CHECKLIST.filter((item) => electricalReadiness?.[item.key] != null);

  return (
    <Card className="p-4">
      <div className="mb-1.5 flex items-center gap-1.5">
        <span aria-hidden="true">🔌</span>
        <p className="text-sm font-semibold text-ink">Electrical readiness</p>
      </div>

      {recorded.length === 0 ? (
        <SimpleStatus
          tone="check"
          headline="Confirmed during your site survey"
          description="An electrician will check your meter, wiring, and earthing when they visit."
        />
      ) : (
        <>
          {(() => {
            const allPass = recorded.every((item) => electricalReadiness?.[item.key] === true);
            return (
              <SimpleStatus
                tone={allPass ? "good" : "check"}
                headline={allPass ? "Your electrical setup looks ready" : "A few electrical items need attention"}
                description={
                  allPass
                    ? "Our site survey confirmed your meter, panel, and wiring are ready for solar."
                    : "Our site survey flagged one or more items your electrician should follow up on."
                }
              />
            );
          })()}
          <ul className="mt-3 space-y-1.5 border-t border-line pt-3">
            {recorded.map((item) => {
              const pass = electricalReadiness?.[item.key] === true;
              return (
                <li key={item.key} className="flex items-center gap-2 text-sm">
                  <span
                    className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full"
                    style={{
                      background: pass ? "var(--good-bg)" : "var(--bad-bg)",
                      color: pass ? "var(--good)" : "var(--bad)",
                    }}
                    aria-hidden="true"
                  >
                    {pass ? <Check size={13} strokeWidth={2} /> : <X size={13} strokeWidth={2} />}
                  </span>
                  <span className="text-ink-soft">{item.label}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Card>
  );
}
