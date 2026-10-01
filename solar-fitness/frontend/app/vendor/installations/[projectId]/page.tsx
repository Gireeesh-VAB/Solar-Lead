import type { Metadata } from "next";
import { InstallationDetailClient } from "./InstallationDetailClient";

export const metadata: Metadata = {
  title: "Installation project",
  description: "Advance install stages, capture QC and geotagged photos, and submit commissioning.",
};

// A thin server shell around a client component, unlike vendor/jobs/
// [jobId]/page.tsx's server-fetched detail: there is no
// getInstallationServer() in lib/api/serverFetch.ts, and this screen is
// used on-site where every panel is interactive anyway (stage advance,
// checklist, camera capture) — server-rendering it would only add a
// second data path to keep in sync.
export default async function VendorInstallationPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <InstallationDetailClient projectId={projectId} />;
}
