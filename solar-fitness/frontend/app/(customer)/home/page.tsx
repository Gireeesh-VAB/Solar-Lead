import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, SunMedium } from "lucide-react";
import { listChecksServer as listChecks } from "@/lib/api/serverFetch";
import { Button } from "@/components/ui/Primitives";
import { CheckCard } from "../_components/CheckCard";

export const metadata: Metadata = {
  title: "Home",
  robots: { index: false, follow: false },
};

export default async function HomePage() {
  // Falls back to an empty list rather than crashing when there's no valid
  // session yet (e.g. an unauthenticated SSR pass before the client-side
  // AuthGuard in the layout redirects to /login) or the backend is briefly
  // unreachable.
  const checks = await listChecks().catch(() => []);
  const recent = checks.slice(0, 3);

  return (
    <div className="mx-auto flex max-w-xl flex-col gap-8">
      <div className="rounded-[var(--radius-app)] border border-line bg-surface p-6 text-center sm:p-8">
        <span
          className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full"
          style={{ background: "var(--warn-bg)", color: "var(--amber)" }}
          aria-hidden="true"
        >
          <SunMedium size={26} strokeWidth={1.75} />
        </span>
        <h1 className="text-xl font-semibold text-ink">Check your rooftop for solar</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm text-ink-soft">
          Point us at a location and we&apos;ll tell you whether solar works there — usually in under a minute.
        </p>
        <Link href="/check/new" className="mt-5 inline-block">
          <Button size="md" className="px-5">
            Check a new location
            <ArrowRight size={15} strokeWidth={1.75} aria-hidden="true" />
          </Button>
        </Link>
      </div>

      {recent.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Recent checks</h2>
            <Link href="/checks" className="text-xs font-medium text-blue hover:underline">
              View all
            </Link>
          </div>
          <div className="space-y-2">
            {recent.map((check) => (
              <CheckCard key={check.id} check={check} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
