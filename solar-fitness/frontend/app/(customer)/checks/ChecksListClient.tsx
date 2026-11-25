"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import type { Site, Verdict } from "@/lib/types";
import { VERDICT_LABEL } from "@/lib/utils";
import { CheckCard } from "../_components/CheckCard";
import { EmptyState } from "@/components/ui/Primitives";
import { ListChecks, SearchX } from "lucide-react";

const VERDICT_FILTERS: (Verdict | "ALL")[] = [
  "ALL",
  "SUITABLE",
  "SUITABLE_SUBJECT_TO_SURVEY",
  "CONDITIONAL",
  "INSUFFICIENT_DATA",
  "NOT_SUITABLE",
];

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.06, delayChildren: 0.05 },
  },
};

export function ChecksListClient({ checks }: { checks: Site[] }) {
  const [filter, setFilter] = useState<Verdict | "ALL">("ALL");

  const filtered = useMemo(
    () => (filter === "ALL" ? checks : checks.filter((c) => c.latestAssessment?.verdict === filter)),
    [checks, filter]
  );

  if (checks.length === 0) {
    return (
      <EmptyState
        icon={<ListChecks size={28} strokeWidth={1.5} />}
        title="No checks yet"
        description="Once you check a location, it'll show up here."
      />
    );
  }

  return (
    <motion.div initial="hidden" animate="show" variants={stagger} className="space-y-5">
      <motion.div variants={fadeUp} className="min-w-0">
        <span className="mb-2 block text-xs font-semibold uppercase tracking-wide text-ink-faint">
          Filter by result
        </span>
        <div
          role="group"
          aria-label="Filter by result"
          className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:overflow-visible sm:px-0"
          style={{ scrollbarWidth: "none" }}
        >
          {VERDICT_FILTERS.map((v) => {
            const active = filter === v;
            const label = v === "ALL" ? "All results" : VERDICT_LABEL[v];
            return (
              <button
                key={v}
                type="button"
                role="button"
                aria-pressed={active}
                onClick={() => setFilter(v)}
                className="inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded-full border px-3.5 py-2 text-xs font-medium transition-all duration-200 min-h-[36px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue"
                style={
                  active
                    ? {
                        background: "linear-gradient(135deg, var(--brand), var(--brand-soft))",
                        color: "#fff",
                        borderColor: "transparent",
                        boxShadow: "var(--shadow-float)",
                      }
                    : {
                        background: "var(--surface)",
                        color: "var(--ink-soft)",
                        borderColor: "var(--line)",
                      }
                }
              >
                {label}
              </button>
            );
          })}
        </div>
      </motion.div>

      {filtered.length === 0 ? (
        <motion.div
          variants={fadeUp}
          className="flex flex-col items-center gap-1.5 rounded-[var(--radius-app)] border border-dashed border-line px-6 py-12 text-center"
        >
          <span className="mb-1 text-ink-faint" aria-hidden="true">
            <SearchX size={22} strokeWidth={1.5} />
          </span>
          <p className="text-sm font-medium text-ink">No checks match this filter</p>
          <p className="max-w-xs text-xs text-ink-faint">Try a different result, or view all checks.</p>
        </motion.div>
      ) : (
        <motion.div variants={stagger} className="space-y-2">
          {filtered.map((check) => (
            <motion.div key={check.id} variants={fadeUp}>
              <CheckCard check={check} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </motion.div>
  );
}
