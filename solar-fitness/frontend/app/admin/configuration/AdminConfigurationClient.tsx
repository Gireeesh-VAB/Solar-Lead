"use client";

import { useState } from "react";
import { usePlatformHealth, useRotateApiKey } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { QuotaBar } from "@/components/admin/QuotaBar";
import { KeyRound } from "lucide-react";

const FEATURE_FLAGS = [
  { key: "vision_refinement", label: "Vision-based boundary refinement", description: "Enable panorama-driven boundary corrections during assessment." },
  { key: "composite_sites", label: "Composite site aggregation", description: "Allow grouping sites under a shared feeder/DT for aggregate capacity." },
  { key: "usn_ocr", label: "USN OCR extraction", description: "Extract unique service numbers from uploaded bills automatically." },
  { key: "vendor_marketplace", label: "Vendor marketplace v2", description: "New job-matching algorithm for vendor assignment." },
];

const MASKED_KEYS = [
  { service: "Google Maps API", masked: "AIza••••••••••••7Qk2" },
  { service: "Solar API", masked: "sol_live_••••••••9f3a" },
  { service: "Vision API", masked: "vis_live_••••••••c81d" },
  { service: "Weather API", masked: "wx_live_••••••••4b7e" },
];

export function AdminConfigurationClient() {
  const health = usePlatformHealth();
  const rotate = useRotateApiKey();
  const [flags, setFlags] = useState<Record<string, boolean>>({
    vision_refinement: true,
    composite_sites: true,
    usn_ocr: false,
    vendor_marketplace: false,
  });
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
        <ul className="divide-y divide-line">
          {FEATURE_FLAGS.map((flag) => (
            <li key={flag.key} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-medium text-ink">{flag.label}</p>
                <p className="text-xs text-ink-soft">{flag.description}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={flags[flag.key]}
                onClick={() => setFlags((f) => ({ ...f, [flag.key]: !f[flag.key] }))}
                className="relative h-6 w-11 shrink-0 rounded-full transition-colors"
                style={{ background: flags[flag.key] ? "var(--slate)" : "var(--surface-2)" }}
              >
                <span
                  className="absolute top-0.5 h-5 w-5 rounded-full bg-paper transition-transform"
                  style={{ transform: flags[flag.key] ? "translateX(22px)" : "translateX(2px)" }}
                />
              </button>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="p-4">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">API keys</h2>
        <ul className="divide-y divide-line">
          {MASKED_KEYS.map((k) => (
            <li key={k.service} className="flex items-center justify-between gap-3 py-3">
              <div>
                <p className="text-sm font-medium text-ink">{k.service}</p>
                <p className="font-mono tabular text-xs text-ink-faint">{k.masked}</p>
              </div>
              <Button variant="secondary" size="sm" onClick={() => setRotateTarget(k.service)} disabled={rotate.isPending}>
                <KeyRound size={13} strokeWidth={1.75} /> Rotate key
              </Button>
            </li>
          ))}
        </ul>
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
