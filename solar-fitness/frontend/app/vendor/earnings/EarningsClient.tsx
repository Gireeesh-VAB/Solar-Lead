"use client";

import { CheckCircle2, Clock3, IndianRupee, ScaleIcon } from "lucide-react";
import { useVendorEarningsSummary, useVendorPayouts } from "@/lib/query/hooks";
import { Card, CardSkeleton, TableSkeleton, ErrorState, EmptyState, Badge } from "@/components/ui/Primitives";
import { EarningsSummaryTile } from "@/components/vendor/EarningsSummaryTile";
import { formatDate } from "@/lib/utils";
import type { PayoutEntryStatus } from "@/lib/types";

const STATUS_TONE: Record<PayoutEntryStatus, "neutral" | "blue" | "amber"> = {
  pending: "amber",
  paid: "blue",
  disputed: "amber",
};

export function EarningsClient() {
  const summary = useVendorEarningsSummary();
  const payouts = useVendorPayouts();

  return (
    <div className="space-y-8">
      <section aria-labelledby="earnings-summary-heading">
        <h2 id="earnings-summary-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Breakdown
        </h2>
        {summary.isLoading && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <CardSkeleton key={i} />
            ))}
          </div>
        )}
        {summary.isError && <ErrorState description="Could not load earnings summary." onRetry={() => summary.refetch()} />}
        {summary.data && (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <EarningsSummaryTile
              label="Pending"
              value={`₹${summary.data.pendingInr.toLocaleString("en-IN")}`}
              icon={<Clock3 size={13} strokeWidth={1.75} aria-hidden="true" />}
              tone="warn"
            />
            <EarningsSummaryTile
              label="Paid"
              value={`₹${summary.data.paidInr.toLocaleString("en-IN")}`}
              icon={<CheckCircle2 size={13} strokeWidth={1.75} aria-hidden="true" />}
              tone="good"
            />
            <EarningsSummaryTile
              label="Disputed"
              value={`₹${summary.data.disputedInr.toLocaleString("en-IN")}`}
              icon={<ScaleIcon size={13} strokeWidth={1.75} aria-hidden="true" />}
              tone="bad"
            />
          </div>
        )}
      </section>

      <section aria-labelledby="payout-history-heading">
        <h2 id="payout-history-heading" className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Payout history
        </h2>
        {payouts.isLoading && <TableSkeleton rows={6} cols={4} />}
        {payouts.isError && <ErrorState description="Could not load payout history." onRetry={() => payouts.refetch()} />}
        {payouts.data && payouts.data.length === 0 && (
          <EmptyState icon={<IndianRupee size={28} strokeWidth={1.5} />} title="No payouts yet" description="Completed jobs will show up here once reconciled." />
        )}
        {payouts.data && payouts.data.length > 0 && (
          <Card className="overflow-x-auto scrollbar-thin p-0">
            <table className="w-full min-w-[640px] text-sm">
              <caption className="sr-only">Payout history with amount, status, date, and method</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th scope="col" className="px-4 py-2 font-medium">Job</th>
                  <th scope="col" className="px-4 py-2 font-medium text-right">Amount</th>
                  <th scope="col" className="px-4 py-2 font-medium">Status</th>
                  <th scope="col" className="px-4 py-2 font-medium">Method</th>
                  <th scope="col" className="px-4 py-2 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {payouts.data.map((p, i) => (
                  <tr key={p.id} className={i % 2 === 1 ? "bg-surface" : undefined}>
                    <td className="px-4 py-2.5 font-mono tabular text-xs text-ink-soft">{p.jobId}</td>
                    <td className="px-4 py-2.5 text-right font-mono tabular text-ink">₹{p.amount.toLocaleString("en-IN")}</td>
                    <td className="px-4 py-2.5">
                      <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                    </td>
                    <td className="px-4 py-2.5 text-ink-soft">{p.method}</td>
                    <td className="px-4 py-2.5 font-mono tabular text-xs text-ink-soft">{formatDate(p.date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </div>
  );
}
