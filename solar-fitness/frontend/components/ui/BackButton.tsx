"use client";

// Mobile/tablet-only "Back" control — every desktop layout already has a
// persistent sidebar or top nav; mobile often doesn't (the admin/vendor
// sidebars are `hidden md:flex`, i.e. gone entirely below that
// breakpoint), so a page reached by drilling in has no way back except
// the browser chrome, which a installed/PWA context may not even show.
//
// Prefers real history (router.back()) so it returns to the ACTUAL
// previous page, same as the requirement asks; falls back to
// `fallbackHref` only when this tab has no in-app history to go back to
// (a fresh load, a bookmark, a shared deep link) — see useCanGoBack()'s
// own comment. Never hardcodes a destination over real history.
import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCanGoBack } from "@/lib/hooks/useCanGoBack";
import { cn } from "@/lib/utils";

export function BackButton({
  fallbackHref,
  showLabel = true,
  className,
}: {
  /** Where to send the user when this tab has no in-app history — e.g. a
   *  portal's own home/dashboard. Never used when real history exists. */
  fallbackHref: string;
  /** Show the "Back" text next to the icon. The icon alone is enough in
   *  a crowded header toolbar; roomier contexts (a standalone auth page)
   *  read better with the label. Either way the button always has a
   *  real "Back" accessible name, shown or not. */
  showLabel?: boolean;
  className?: string;
}) {
  const router = useRouter();
  const canGoBack = useCanGoBack();

  return (
    <button
      type="button"
      onClick={() => (canGoBack ? router.back() : router.push(fallbackHref))}
      aria-label="Back"
      className={cn(
        // -ml-1.5 offsets the icon's own inner padding so it optically
        // aligns with the edge content around it lines up against,
        // instead of reading as indented relative to a sibling logo/title.
        // min-h/min-w-[44px] — same touch-target floor
        // app/(customer)/profile/ProfileForm.tsx's inputs already use.
        "flex md:hidden shrink-0 -ml-1.5 min-h-[44px] min-w-[44px] items-center justify-center gap-1 rounded-[var(--radius-app)] pl-1.5 pr-2.5 text-sm font-medium text-ink-soft transition-colors hover:bg-surface-2 hover:text-ink active:bg-surface-2",
        className
      )}
    >
      <ArrowLeft size={20} strokeWidth={1.75} aria-hidden="true" />
      {showLabel && <span>Back</span>}
    </button>
  );
}
