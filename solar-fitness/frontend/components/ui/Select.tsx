import type { SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

/** The filter/picker dropdown, in one place.
 *
 *  The same ad-hoc class string was repeated on every `<select>` in the
 *  vendor portal (job filters, stage filters, the installation pickers),
 *  each drifting slightly on focus colour and padding. This is a thin
 *  styled wrapper — no behaviour, every native prop forwarded — so the
 *  focus ring stays on `--brand` everywhere and the control keeps a
 *  comfortable touch target on site. */
export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "cursor-pointer rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink",
        "outline-none transition-colors hover:border-ink-faint/60",
        "focus:border-brand focus:ring-2 focus:ring-brand/25",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    />
  );
}
