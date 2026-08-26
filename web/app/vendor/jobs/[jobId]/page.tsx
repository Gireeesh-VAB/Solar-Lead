import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CalendarClock, IndianRupee, ListChecks, MapPin } from "lucide-react";
import { getVendorJob, getSite } from "@/lib/api/client";
import { Card, PageHeader } from "@/components/ui/Primitives";
import { SlaBadge } from "@/components/vendor/SlaBadge";
import { siteTypeLabel, formatDate } from "@/lib/utils";
import { JobActions } from "./JobActions";

export async function generateMetadata({ params }: { params: Promise<{ jobId: string }> }): Promise<Metadata> {
  const { jobId } = await params;
  const job = await getVendorJob(jobId).catch(() => null);
  if (!job) return { title: "Job not found" };
  return {
    title: `${job.siteName} — job`,
    description: `Vendor job at ${job.siteName}, ${job.district}, ${job.state}: deadline, payout, and capture requirements.`,
  };
}

export default async function VendorJobDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const job = await getVendorJob(jobId).catch(() => null);
  if (!job) notFound();
  const site = await getSite(job.siteId).catch(() => null);

  return (
    <div className="space-y-6">
      <PageHeader
        title={job.siteName}
        description={`${siteTypeLabel(job.siteType)} · ${job.district}, ${job.state}`}
        actions={<SlaBadge status={job.status} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-6">
          <Card className="p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <MapPin size={15} strokeWidth={1.75} aria-hidden="true" />
              {site?.address ?? `${job.district}, ${job.state}`}
            </div>
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <CalendarClock size={15} strokeWidth={1.75} aria-hidden="true" />
              Deadline: {formatDate(job.deadline)}
            </div>
            <div className="flex items-center gap-2 font-mono tabular text-sm text-ink">
              <IndianRupee size={15} strokeWidth={1.75} aria-hidden="true" />
              Payout: ₹{job.payoutInr.toLocaleString("en-IN")}
            </div>
          </Card>

          <section aria-labelledby="requirements-heading">
            <h2 id="requirements-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              <ListChecks size={14} strokeWidth={1.75} aria-hidden="true" />
              Requirements
            </h2>
            <Card className="p-4">
              <ul className="space-y-2 text-sm text-ink">
                {job.requirements.map((req) => (
                  <li key={req} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-teal" aria-hidden="true" />
                    {req}
                  </li>
                ))}
              </ul>
            </Card>
          </section>
        </div>

        <div className="space-y-6">
          <section aria-labelledby="actions-heading">
            <h2 id="actions-heading" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Actions
            </h2>
            <JobActions job={job} />
          </section>
        </div>
      </div>
    </div>
  );
}
