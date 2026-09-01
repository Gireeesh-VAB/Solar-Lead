import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getVendorJobServer as getVendorJob, getSiteServer as getSite } from "@/lib/api/serverFetch";
import { PageHeader } from "@/components/ui/Primitives";
import { CaptureTabs } from "./CaptureTabs";

export async function generateMetadata({ params }: { params: Promise<{ jobId: string }> }): Promise<Metadata> {
  const { jobId } = await params;
  const job = await getVendorJob(jobId).catch(() => null);
  return {
    title: job ? `Capture — ${job.siteName}` : "Capture",
    description: "Capture boundary and USN data for this job site.",
  };
}

export default async function VendorJobCapturePage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const job = await getVendorJob(jobId).catch(() => null);
  if (!job) notFound();
  const site = await getSite(job.siteId).catch(() => null);
  if (!site) notFound();

  const showUsn = site.siteType === "ROOFTOP_RESIDENTIAL" || site.siteType === "ROOFTOP_CI";

  return (
    <div className="space-y-6">
      <PageHeader title={`Capture — ${job.siteName}`} description="Draw the site boundary and, where applicable, confirm the USN." />
      <CaptureTabs site={site} showUsn={showUsn} />
    </div>
  );
}
