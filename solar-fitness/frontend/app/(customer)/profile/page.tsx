import type { Metadata } from "next";
import { getCustomerProfileServer as getCustomerProfile } from "@/lib/api/serverFetch";
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
    <div className="mx-auto max-w-md">
      <ProfileForm profile={profile} />
    </div>
  );
}
