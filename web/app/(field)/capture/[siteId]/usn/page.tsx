import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getSite } from "@/lib/api/client";
import { UsnCaptureFlow } from "@/components/sites/UsnCaptureFlow";

export async function generateMetadata({ params }: { params: Promise<{ siteId: string }> }): Promise<Metadata> {
  const { siteId } = await params;
  const site = await getSite(siteId).catch(() => null);
  return { title: site ? `Capture USN — ${site.name}` : "Capture USN", description: "Field USN capture via camera-first OCR or manual entry." };
}

export default async function FieldUsnPage({ params }: { params: Promise<{ siteId: string }> }) {
  const { siteId } = await params;
  const site = await getSite(siteId).catch(() => null);
  if (!site) notFound();
  if (site.siteType !== "ROOFTOP_RESIDENTIAL" && site.siteType !== "ROOFTOP_CI") notFound();
  return (
    <div className="space-y-3">
      <h1 className="text-lg font-semibold text-ink">{site.name}</h1>
      <p className="text-sm text-ink-soft">Capture the USN from an electricity bill or payment proof, or enter it manually.</p>
      <UsnCaptureFlow site={site} mobile />
    </div>
  );
}
