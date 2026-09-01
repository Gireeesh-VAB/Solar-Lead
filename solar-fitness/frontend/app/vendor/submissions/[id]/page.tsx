import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { getVendorJobServer as getVendorJob } from "@/lib/api/serverFetch";
import { Card, PageHeader } from "@/components/ui/Primitives";
import { formatDate } from "@/lib/utils";
import { DisputeAction } from "./DisputeAction";

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  const job = await getVendorJob(id).catch(() => null);
  if (!job) return { title: "Submission not found" };
  return {
    title: `${job.siteName} — submission`,
    description: `Reconciliation detail for ${job.siteName}: submitted vs measured capacity and payout variance.`,
  };
}

export default async function VendorSubmissionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const job = await getVendorJob(id).catch(() => null);
  if (!job || job.status !== "submitted") notFound();

  const variance = job.variancePct ?? 0;
  const VarianceIcon = variance > 0 ? ArrowUpRight : variance < 0 ? ArrowDownRight : Minus;
  const varianceColor = Math.abs(variance) > 10 ? "var(--bad)" : Math.abs(variance) > 5 ? "var(--warn)" : "var(--good)";

  return (
    <div className="space-y-6">
      <PageHeader title={job.siteName} description={`${job.district}, ${job.state} · Submitted ${job.submittedAt ? formatDate(job.submittedAt) : "—"}`} />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Estimated capacity</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{job.estimatedCapacityKwp ?? "—"} kWp</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Measured capacity</p>
          <p className="mt-1 font-mono tabular text-2xl text-ink">{job.measuredCapacityKwp ?? "—"} kWp</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Variance</p>
          <p className="mt-1 flex items-center gap-1 font-mono tabular text-2xl" style={{ color: varianceColor }}>
            <VarianceIcon size={18} strokeWidth={1.75} aria-hidden="true" />
            {variance > 0 ? "+" : ""}
            {variance}%
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Submitted payout</p>
          <p className="mt-1 font-mono tabular text-xl text-ink">₹{job.payoutInr.toLocaleString("en-IN")}</p>
        </Card>
        <Card className="p-4">
          <p className="text-xs text-ink-soft">Reconciled payout</p>
          <p className="mt-1 font-mono tabular text-xl text-ink">₹{(job.reconciledPayoutInr ?? job.payoutInr).toLocaleString("en-IN")}</p>
        </Card>
      </div>

      <section aria-labelledby="dispute-heading">
        <h2 id="dispute-heading" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Dispute
        </h2>
        <DisputeAction job={job} />
      </section>
    </div>
  );
}
