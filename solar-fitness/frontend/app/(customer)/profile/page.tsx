import type { Metadata } from "next";
import { getCustomerProfileServer as getCustomerProfile } from "@/lib/api/serverFetch";
import { PageHeader } from "@/components/ui/Primitives";
import { ProfileForm } from "./ProfileForm";

export const metadata: Metadata = {
  title: "Profile",
  robots: { index: false, follow: false },
};

export default async function ProfilePage() {
  // Falls through to a blank render rather than crashing on an
  // unauthenticated SSR pass — the layout's client-side AuthGuard redirects
  // to /login a moment after hydration in that case.
  const profile = await getCustomerProfile().catch(() => null);
  if (!profile) return null;
  return (
    <div className="mx-auto max-w-md space-y-6">
      <PageHeader title="Profile" description="Your personal details." />
      <ProfileForm profile={profile} />
    </div>
  );
}
