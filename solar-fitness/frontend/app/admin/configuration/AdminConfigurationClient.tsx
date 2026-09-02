"use client";

import { useState } from "react";
import { usePlatformHealth, useRotateApiKey, useFeatureFlags, useSetFeatureFlag, useServiceApiKeys } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button } from "@/components/ui/Primitives";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { QuotaBar } from "@/components/admin/QuotaBar";
import { KeyRound } from "lucide-react";

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
                  style={{ background: flag.enabled ? "var(--slate)" : "var(--surface-2)" }}
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
