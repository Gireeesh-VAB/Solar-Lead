import { CheckCircle2, CircleAlert, CircleHelp, CircleSlash, ShieldQuestion } from "lucide-react";
import type { Verdict } from "@/lib/types";
import { VERDICT_LABEL, cn } from "@/lib/utils";

const STYLE: Record<Verdict, { bg: string; fg: string; Icon: typeof CheckCircle2 }> = {
  SUITABLE: { bg: "var(--good-bg)", fg: "var(--good)", Icon: CheckCircle2 },
  SUITABLE_SUBJECT_TO_SURVEY: { bg: "var(--warn-bg)", fg: "var(--warn)", Icon: ShieldQuestion },
  CONDITIONAL: { bg: "var(--warn-bg)", fg: "var(--warn)", Icon: CircleAlert },
  INSUFFICIENT_DATA: { bg: "var(--neutral-bg)", fg: "var(--neutral-verdict)", Icon: CircleHelp },
  NOT_SUITABLE: { bg: "var(--bad-bg)", fg: "var(--bad)", Icon: CircleSlash },
};

export function VerdictChip({
  verdict,
  size = "md",
  className,
}: {
  verdict: Verdict;
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const { bg, fg, Icon } = STYLE[verdict];
  const sizeCls =
    size === "lg" ? "text-base px-3 py-1.5 gap-2" : size === "sm" ? "text-xs px-2 py-0.5 gap-1" : "text-sm px-2.5 py-1 gap-1.5";
  return (
    <span
      className={cn("inline-flex items-center rounded-[var(--radius-app)] font-medium border", sizeCls, className)}
      style={{ background: bg, color: fg, borderColor: fg + "33" }}
      role="status"
      aria-label={`Verdict: ${VERDICT_LABEL[verdict]}`}
    >
      <Icon size={size === "lg" ? 18 : size === "sm" ? 12 : 14} strokeWidth={1.75} aria-hidden="true" />
      {VERDICT_LABEL[verdict]}
    </span>
  );
}
