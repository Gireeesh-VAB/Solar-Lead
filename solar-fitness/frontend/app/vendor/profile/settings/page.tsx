import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { ProfileTabs } from "@/components/vendor/ProfileTabs";
import { VendorSettingsClient } from "@/components/vendor/VendorSettingsClient";

export const metadata: Metadata = {
  title: "Settings",
  description: "Account, security, notifications, availability, and appearance.",
};

export default function VendorSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Manage your account and application preferences." />
      <ProfileTabs />
      <VendorSettingsClient />
    </div>
  );
}
