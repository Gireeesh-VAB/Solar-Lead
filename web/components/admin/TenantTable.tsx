import Link from "next/link";
import type { Tenant } from "@/lib/types";
import { EmptyState } from "@/components/ui/Primitives";
import { formatDate } from "@/lib/utils";
import { Building2 } from "lucide-react";

const TIER_LABEL: Record<Tenant["tier"], string> = {
  starter: "Starter",
  growth: "Growth",
  enterprise: "Enterprise",
};

const STATUS_TONE: Record<Tenant["status"], { color: string; bg: string }> = {
  active: { color: "var(--good)", bg: "var(--good-bg)" },
  trial: { color: "var(--warn)", bg: "var(--warn-bg)" },
  suspended: { color: "var(--bad)", bg: "var(--bad-bg)" },
  churned: { color: "var(--ink-faint)", bg: "var(--neutral-bg)" },
};

export function TenantTable({ tenants }: { tenants: Tenant[] }) {
  if (tenants.length === 0) {
    return <EmptyState icon={<Building2 size={28} strokeWidth={1.5} />} title="No tenants match these filters" description="Try widening your search or filters." />;
  }
  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full min-w-[900px] text-sm">
        <caption className="sr-only">Tenant list with tier, status, seats, and usage</caption>
        <thead>
          <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
            <th scope="col" className="py-2 pr-3 font-medium">Tenant</th>
            <th scope="col" className="py-2 pr-3 font-medium">Tier</th>
            <th scope="col" className="py-2 pr-3 font-medium">Status</th>
            <th scope="col" className="py-2 pr-3 font-medium text-right">Seats</th>
            <th scope="col" className="py-2 pr-3 font-medium text-right">Sites this month</th>
            <th scope="col" className="py-2 pr-3 font-medium text-right">API calls</th>
            <th scope="col" className="py-2 pr-3 font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {tenants.map((t, i) => (
            <tr key={t.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
              <td className="py-2.5 pr-3">
                <Link href={`/admin/tenants/${t.id}`} className="font-medium text-ink hover:text-slate">
                  {t.name}
                </Link>
                <p className="font-mono tabular text-xs text-ink-faint">{t.id}</p>
              </td>
              <td className="py-2.5 pr-3 text-ink-soft">{TIER_LABEL[t.tier]}</td>
              <td className="py-2.5 pr-3">
                <span
                  className="inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium capitalize"
                  style={{ color: STATUS_TONE[t.status].color, background: STATUS_TONE[t.status].bg }}
                >
                  {t.status}
                </span>
              </td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{t.seatCount}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{t.sitesAssessedThisMonth.toLocaleString("en-IN")}</td>
              <td className="py-2.5 pr-3 text-right font-mono tabular text-ink">{t.apiCallsThisMonth.toLocaleString("en-IN")}</td>
              <td className="py-2.5 pr-3 font-mono tabular text-xs text-ink-soft">{formatDate(t.createdAt)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
