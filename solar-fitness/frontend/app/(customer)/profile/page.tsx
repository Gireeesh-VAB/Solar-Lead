import type { Metadata } from "next";
import { getCustomerProfile } from "@/lib/api/client";
import { PageHeader } from "@/components/ui/Primitives";
import { ProfileForm } from "./ProfileForm";

export const metadata: Metadata = {
  title: "Profile",
  robots: { index: false, follow: false },
};

export default async function ProfilePage() {
  const profile = await getCustomerProfile();
  return (
    <div className="mx-auto max-w-md space-y-6">
      <PageHeader title="Profile" description="Your personal details." />
      <ProfileForm profile={profile} />
    </div>
  );
}
