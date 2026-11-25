import { CheckCircle2, CircleSlash, HelpCircle, Sun } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusTone = "good" | "check" | "bad";

const TONE_STYLE: Record<StatusTone, { bg: string; fg: string; Icon: typeof CheckCircle2 }> = {
  good: { bg: "var(--good-bg)", fg: "var(--good)", Icon: CheckCircle2 },
  check: { bg: "var(--warn-bg)", fg: "var(--warn)", Icon: HelpCircle },
  bad: { bg: "var(--bad-bg)", fg: "var(--bad)", Icon: CircleSlash },
};

/** A big-icon plain-language status banner — the "🟢 GOOD / 🟡 CHECK
 *  NEEDED / 🔴 NOT SUITABLE" pattern used throughout the simple-first
 *  redesign, built on the same --good/--warn/--bad tokens VerdictChip
 *  already uses so the two stay visually consistent. */
export function SimpleStatus({
  tone,
  headline,
  description,
  sunRating,
  size = "md",
  className,
}: {
  tone: StatusTone;
  headline: string;
  description?: string;
  /** 0-5 filled suns, shown instead of the tone icon — for the sunlight
   *  card, where "how much sun" reads better as a rating than a chip. */
  sunRating?: number;
  size?: "sm" | "md";
  className?: string;
}) {
  const { bg, fg, Icon } = TONE_STYLE[tone];
  const iconSize = size === "sm" ? 20 : 26;

  return (
    <div className={cn("flex items-start gap-3", className)}>
      <span
        className="flex shrink-0 items-center justify-center rounded-full"
        style={{ background: bg, color: fg, width: iconSize + 20, height: iconSize + 20 }}
        aria-hidden="true"
      >
        {sunRating != null ? <Sun size={iconSize} strokeWidth={1.75} /> : <Icon size={iconSize} strokeWidth={1.75} />}
      </span>
      <div className="min-w-0 pt-0.5">
        <p className={cn("font-semibold text-ink", size === "sm" ? "text-sm" : "text-base")}>{headline}</p>
        {sunRating != null && (
          <div className="mt-1 flex items-center gap-0.5" role="img" aria-label={`${sunRating} out of 5`}>
            {Array.from({ length: 5 }).map((_, i) => (
              <Sun
                key={i}
                size={14}
                strokeWidth={1.75}
                style={{ color: i < sunRating ? "var(--amber)" : "var(--line)" }}
                aria-hidden="true"
              />
            ))}
          </div>
        )}
        {description && <p className="mt-1 text-sm text-ink-soft">{description}</p>}
      </div>
    </div>
  );
}
