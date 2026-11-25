"use client";

// The premium, page-level counterpart to TechnicalDetails.tsx's small inline
// disclosure — a top-level accordion for grouping the Result Page's existing
// cards into named sections. Reuses Card's own "interactive" hover treatment
// (Primitives.tsx) rather than inventing a second hover style, and the same
// chevron-rotation technique TechnicalDetails already uses, so this reads as
// a natural extension of the existing pattern rather than a competing one.
//
// Deliberately does NOT strip or restyle whatever is passed as children —
// lib/utils.ts's cn() is a plain class-join, not tailwind-merge, so trying to
// override a child Card's baked-in border/bg via extra classNames would be a
// specificity gamble. Instead the content panel gets its own tinted
// background (bg-surface-2) so existing child Cards read as grouped tiles
// sitting inside one section, not boxes nested in boxes.
//
// Children are only mounted once a section has been opened at least once
// (`hasOpened`), then stay mounted across further collapses — sections that
// start collapsed never fire their data hooks, load the map, or spin up the
// 3D viewer until the user actually asks for them.

import { Children, useId, useState, type ReactNode } from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";
import { ChevronDown, type LucideIcon } from "lucide-react";
import { Card } from "./Primitives";
import { cn } from "@/lib/utils";

type Tone = "brand" | "amber" | "good" | "blue" | "teal" | "neutral";

const TONE_STYLE: Record<Tone, { bg: string; color: string }> = {
  brand: { bg: "var(--surface-2)", color: "var(--brand)" },
  amber: { bg: "var(--warn-bg)", color: "var(--amber)" },
  good: { bg: "var(--good-bg)", color: "var(--good)" },
  blue: { bg: "var(--surface-2)", color: "var(--blue)" },
  teal: { bg: "var(--teal-soft, rgba(20,148,132,0.12))", color: "var(--teal)" },
  neutral: { bg: "var(--surface-2)", color: "var(--ink-soft)" },
};

const EASE_OUT = [0.4, 0, 0.2, 1] as const;
const EASE_IN = [0.4, 0, 1, 1] as const;

const contentVariants: Variants = {
  collapsed: {
    height: 0,
    opacity: 0,
    transition: { height: { duration: 0.3, ease: EASE_IN }, opacity: { duration: 0.15 } },
  },
  open: {
    height: "auto",
    opacity: 1,
    transition: {
      height: { duration: 0.35, ease: EASE_OUT },
      opacity: { duration: 0.25, delay: 0.08 },
      when: "beforeChildren",
      staggerChildren: 0.06,
      delayChildren: 0.1,
    },
  },
};

const itemVariants: Variants = {
  collapsed: { opacity: 0, y: -8 },
  open: { opacity: 1, y: 0, transition: { duration: 0.25, ease: EASE_OUT } },
};

export function ExpandableSection({
  icon: Icon,
  title,
  summary,
  defaultOpen = false,
  tone = "brand",
  className,
  children,
}: {
  icon: LucideIcon;
  title: string;
  summary?: ReactNode;
  defaultOpen?: boolean;
  tone?: Tone;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [hasOpened, setHasOpened] = useState(defaultOpen);
  const shouldReduceMotion = useReducedMotion();
  const panelId = useId();
  const { bg, color } = TONE_STYLE[tone];

  const toggle = () => {
    setOpen((v) => !v);
    setHasOpened(true);
  };

  const items = Children.toArray(children);

  return (
    <Card interactive className={cn("overflow-hidden", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls={panelId}
        className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-surface-2/60 sm:px-5"
      >
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
          style={{ background: bg, color }}
          aria-hidden="true"
        >
          <Icon size={17} strokeWidth={1.75} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-ink">{title}</span>
          {summary && <span className="mt-0.5 block truncate text-xs text-ink-soft">{summary}</span>}
        </span>
        <ChevronDown
          size={18}
          strokeWidth={1.75}
          className={cn("shrink-0 text-ink-faint transition-transform duration-300", open && "rotate-180")}
          aria-hidden="true"
        />
      </button>

      {shouldReduceMotion ? (
        open && (
          <div id={panelId} className="border-t border-line bg-surface-2 px-4 py-4 sm:px-5">
            <div className="space-y-3">{hasOpened && items}</div>
          </div>
        )
      ) : (
        <motion.div
          id={panelId}
          initial={defaultOpen ? "open" : "collapsed"}
          animate={open ? "open" : "collapsed"}
          variants={contentVariants}
          style={{ overflow: "hidden" }}
        >
          <div className="border-t border-line bg-surface-2 px-4 py-4 sm:px-5">
            <div className="space-y-3">
              {hasOpened &&
                items.map((item, i) => (
                  <motion.div key={i} variants={itemVariants}>
                    {item}
                  </motion.div>
                ))}
            </div>
          </div>
        </motion.div>
      )}
    </Card>
  );
}
