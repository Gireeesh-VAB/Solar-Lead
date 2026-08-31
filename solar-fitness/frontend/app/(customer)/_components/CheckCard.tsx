import Link from "next/link";
import { MapPin } from "lucide-react";
import type { Site } from "@/lib/types";
import { Card } from "@/components/ui/Primitives";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { formatDate, formatKwp } from "@/lib/utils";

export function CheckCard({ check }: { check: Site }) {
  const assessment = check.latestAssessment;
  return (
    <Link href={`/check/${check.id}/result`}>
      <Card className="flex items-center gap-3 p-3.5 transition-colors hover:border-blue">
        <span
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
          style={{ background: "var(--surface-2)", color: "var(--blue)" }}
          aria-hidden="true"
        >
          <MapPin size={16} strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{check.name}</p>
          <p className="truncate text-xs text-ink-faint">{check.address}</p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          {assessment ? <VerdictChip verdict={assessment.verdict} size="sm" /> : <span className="text-xs text-ink-faint">Processing…</span>}
          <span className="text-[11px] text-ink-faint">
            {assessment && assessment.capacityKwp > 0 ? formatKwp(assessment.capacityKwp) : "—"} · {formatDate(check.createdAt)}
          </span>
        </div>
      </Card>
    </Link>
  );
}
