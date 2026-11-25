import type { Metadata } from "next";
import { listChecksServer as listChecks } from "@/lib/api/serverFetch";
import { PageHeader } from "@/components/ui/Primitives";
import { ChecksListClient } from "./ChecksListClient";

export const metadata: Metadata = {
  title: "My Checks",
  robots: { index: false, follow: false },
};

export default async function ChecksPage() {
  // See home/page.tsx — falls back to empty rather than crashing on an
  // unauthenticated SSR pass or a briefly unreachable backend.
  const checks = await listChecks().catch(() => []);
  return (
    <div className="mx-auto flex max-w-xl flex-col gap-6 sm:gap-8">
      <PageHeader title="My checks" description="Every location you've checked, with its latest result." />
      <ChecksListClient checks={checks} />
    </div>
  );
}
