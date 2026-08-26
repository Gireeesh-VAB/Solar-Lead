import type { ReactNode } from "react";
import { Card } from "@/components/ui/Primitives";

export function EarningsSummaryTile({
  label,
  value,
  icon,
  tone,
}: {
  label: string;
  value: string;
  icon?: ReactNode;
  tone?: "good" | "warn" | "bad" | "neutral";
}) {
  const color =
    tone === "good" ? "var(--good)" : tone === "warn" ? "var(--warn)" : tone === "bad" ? "var(--bad)" : "var(--ink)";
  return (
    <Card className="p-4">
      <div className="flex items-center gap-1.5 text-xs text-ink-soft">
        {icon}
        {label}
      </div>
      <p className="mt-1 font-mono tabular text-2xl" style={{ color }}>
        {value}
      </p>
    </Card>
  );
}
