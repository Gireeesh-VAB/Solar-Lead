import type { Metadata } from "next";
import { listChecksServer as listChecks } from "@/lib/api/serverFetch";
import { HomeClient } from "./HomeClient";

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

  return <HomeClient checks={checks} />;
}
