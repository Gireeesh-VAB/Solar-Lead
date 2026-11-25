"use client";

// A tap-to-open plain-language explanation for the handful of jargon
// words that have to stay visible in the simple-first view (e.g.
// "confidence"). No external popover library — just a toggled inline
// card, closed by an outside click/tap or Escape.

import { useEffect, useRef, useState } from "react";
import { Info } from "lucide-react";

export function InfoTip({ children, label = "What does this mean?" }: { children: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: PointerEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={label}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-ink-faint hover:text-ink-soft"
      >
        <Info size={13} strokeWidth={1.75} aria-hidden="true" />
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-20 mb-1.5 w-48 -translate-x-1/2 rounded-[var(--radius-app)] border border-line bg-surface px-2.5 py-2 text-left text-xs font-normal leading-relaxed text-ink-soft shadow-[var(--shadow-float)]"
        >
          {children}
        </span>
      )}
    </span>
  );
}
