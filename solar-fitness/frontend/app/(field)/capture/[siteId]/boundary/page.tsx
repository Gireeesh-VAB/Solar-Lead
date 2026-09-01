import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getSiteServer as getSite } from "@/lib/api/serverFetch";
import { FieldBoundaryCapture } from "@/components/field/FieldBoundaryCapture";

export async function generateMetadata({ params }: { params: Promise<{ siteId: string }> }): Promise<Metadata> {
  const { siteId } = await params;
  const site = await getSite(siteId).catch(() => null);
  return { title: site ? `Capture boundary — ${site.name}` : "Capture boundary", description: "Field boundary capture for site survey." };
}

export default async function FieldBoundaryPage({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = await params;
  const site = await getSite(siteId).catch(() => null);
  if (!site) notFound();
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold text-ink">{site.name}</h1>
      <p className="text-sm text-ink-soft">Draw the site boundary and close the polygon to submit.</p>
      <FieldBoundaryCapture site={site} />
    </div>
  );
}
