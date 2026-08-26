import type { Metadata } from "next";
import { listChecks } from "@/lib/api/client";
import { PageHeader } from "@/components/ui/Primitives";
import { ChecksListClient } from "./ChecksListClient";

export const metadata: Metadata = {
  title: "My Checks",
  robots: { index: false, follow: false },
};

export default async function ChecksPage() {
  const checks = await listChecks();
  return (
    <div className="space-y-6">
      <PageHeader title="My checks" description="Every location you've checked, with its latest result." />
      <ChecksListClient checks={checks} />
    </div>
  );
}
