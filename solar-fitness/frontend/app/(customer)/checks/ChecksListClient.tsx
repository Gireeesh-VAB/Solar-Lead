"use client";

import { useMemo, useState } from "react";
import type { Site, Verdict } from "@/lib/types";
import { VERDICT_LABEL } from "@/lib/utils";
import { CheckCard } from "../_components/CheckCard";
import { EmptyState } from "@/components/ui/Primitives";
import { ListChecks } from "lucide-react";

const VERDICT_FILTERS: (Verdict | "ALL")[] = [
  "ALL",
  "SUITABLE",
  "SUITABLE_SUBJECT_TO_SURVEY",
  "CONDITIONAL",
  "INSUFFICIENT_DATA",
  "NOT_SUITABLE",
];

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
    <div className="space-y-4">
      <label className="block text-sm">
        <span className="mb-1 block font-medium text-ink">Filter by result</span>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as Verdict | "ALL")}
          className="w-full max-w-xs rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue sm:w-auto"
        >
          {VERDICT_FILTERS.map((v) => (
            <option key={v} value={v}>
              {v === "ALL" ? "All results" : VERDICT_LABEL[v]}
            </option>
          ))}
        </select>
      </label>

      {filtered.length === 0 ? (
        <p className="text-sm text-ink-soft">No checks match this filter.</p>
      ) : (
        <div className="space-y-2">
          {filtered.map((check) => (
            <CheckCard key={check.id} check={check} />
          ))}
        </div>
      )}
    </div>
  );
}
