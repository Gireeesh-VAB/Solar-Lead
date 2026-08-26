import Link from "next/link";
import type { Site } from "@/lib/types";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { formatKwp, siteTypeLabel, formatDate } from "@/lib/utils";
import { EmptyState } from "@/components/ui/Primitives";
import { Building2 } from "lucide-react";

export function SiteTable({ sites }: { sites: Site[] }) {
  if (sites.length === 0) {
    return (
      <EmptyState
        icon={<Building2 size={28} strokeWidth={1.5} />}
        title="No sites match these filters"
        description="Try widening your filters, or import a new batch of candidate sites."
      />
    );
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[900px] text-sm">
        <caption className="sr-only">Site portfolio with verdict, capacity, and confidence per site</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th scope="col" className="py-2 pr-3 font-medium">Site</th>
            <th scope="col" className="py-2 pr-3 font-medium">Type</th>
            <th scope="col" className="py-2 pr-3 font-medium">District / State</th>
            <th scope="col" className="py-2 pr-3 font-medium">Verdict</th>
            <th scope="col" className="py-2 pr-3 font-medium text-right">Capacity</th>
            <th scope="col" className="py-2 pr-3 font-medium">Confidence</th>
            <th scope="col" className="py-2 pr-3 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {sites.map((site, i) => (
            <tr key={site.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
              <td className="py-2.5 pr-3">
                <Link href={`/sites/${site.id}`} className="font-medium text-ink hover:text-amber">
                  {site.name}
                </Link>
                <p className="font-mono tabular text-xs text-ink-faint">{site.id}</p>
              </td>
              <td className="py-2.5 pr-3 text-ink-soft">{siteTypeLabel(site.siteType)}</td>
              <td className="py-2.5 pr-3 text-ink-soft">
                {site.district}, {site.state}
              </td>
              <td className="py-2.5 pr-3">
                {site.latestAssessment ? (
                  <VerdictChip verdict={site.latestAssessment.verdict} size="sm" />
                ) : (
                  <span className="text-xs text-ink-faint">Not assessed</span>
                )}
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">
                {site.latestAssessment && site.latestAssessment.capacityKwp > 0 ? formatKwp(site.latestAssessment.capacityKwp) : "—"}
              </td>
              <td className="py-2.5 pr-3">
                {site.latestAssessment ? <ConfidenceMeter tier={site.latestAssessment.confidence} /> : "—"}
              </td>
              <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(site.updatedAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
