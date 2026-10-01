"use client";

import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

/** Read-only display or an interactive 1-5 picker, depending on whether
 *  `onChange` is passed — one component for both the vendor card's
 *  average-rating display and the "rate this vendor" form, rather than
 *  two near-identical star renderers. */
export function StarRating({
  value,
  onChange,
  size = 14,
}: {
  value: number;
  onChange?: (value: number) => void;
  size?: number;
}) {
  const readOnly = !onChange;
  return (
    <div
      className={cn("inline-flex items-center gap-0.5", !readOnly && "cursor-pointer")}
      role={readOnly ? "img" : "radiogroup"}
      aria-label={readOnly ? `${value.toFixed(1)} out of 5 stars` : "Rating"}
    >
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          type="button"
          disabled={readOnly}
          aria-label={readOnly ? undefined : `${star} star${star > 1 ? "s" : ""}`}
          aria-pressed={readOnly ? undefined : value >= star}
          tabIndex={readOnly ? -1 : 0}
          onClick={() => onChange?.(star)}
          className={readOnly ? "cursor-default" : undefined}
        >
          <Star
            size={size}
            strokeWidth={1.75}
            className={star <= Math.round(value) ? "fill-current text-amber" : "text-ink-faint"}
          />
        </button>
      ))}
    </div>
  );
}
