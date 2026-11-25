import type { Metadata } from "next";
import { InstallationReviewClient } from "./InstallationReviewClient";

export const metadata: Metadata = {
  title: "Installation review",
  description: "Review the vendor's QC checklist and commissioning record, and approve both.",
};

export default async function AdminInstallationPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <InstallationReviewClient projectId={projectId} />;
}
