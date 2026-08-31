import type { ConfidenceTier } from "@/lib/types";
import { cn } from "@/lib/utils";

const LEVEL: Record<ConfidenceTier, number> = { High: 3, Medium: 2, Low: 1, "N/A": 0 };

export function ConfidenceMeter({ tier, className }: { tier: ConfidenceTier; className?: string }) {
  const level = LEVEL[tier];
  return (
    <div className={cn("inline-flex items-center gap-2", className)} aria-label={`Confidence: ${tier}`}>
      <div className="flex items-end gap-0.5" aria-hidden="true">
        {[1, 2, 3].map((bar) => (
          <span
            key={bar}
            className="block w-1.5 rounded-[2px]"
            style={{
              height: 6 + bar * 4,
              background: bar <= level ? "var(--blue)" : "var(--line)",
            }}
          />
        ))}
      </div>
      <span className="text-sm text-ink-soft">{tier} confidence</span>
    </div>
  );
}
