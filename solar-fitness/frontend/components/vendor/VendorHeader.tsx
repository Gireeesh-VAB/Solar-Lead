"use client";

import Link from "next/link";
import { Search, Sun } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";
import { NotificationBell } from "@/components/layout/NotificationBell";
import { BackButton } from "@/components/ui/BackButton";
import { MobileNavDrawer } from "@/components/layout/MobileNavDrawer";
import { VENDOR_NAV } from "@/components/vendor/VendorSidebar";

export function VendorHeader() {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-paper px-4 py-3 md:px-6">
      <div className="flex flex-1 items-center gap-2">
        <MobileNavDrawer title="Solar Site Fitness" subtitle="Vendor portal" icon={Sun} groups={VENDOR_NAV} />
        <BackButton fallbackHref="/vendor/dashboard" showLabel={false} />
        <Link
          href="/vendor/jobs"
          className="flex max-w-sm flex-1 items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft hover:border-brand"
        >
          <Search size={15} strokeWidth={1.75} aria-hidden="true" />
          Search jobs, sites, districts…
        </Link>
      </div>
      <div className="flex items-center gap-3">
        <NotificationBell />
        <UserMenu
          name="Demo Surveyor"
          role="Vendor · Demo Surveyor"
          initials="DS"
          profileHref="/vendor/profile"
          settingsHref="/vendor/profile/settings"
          accentVar="var(--brand)"
        />
      </div>
    </header>
  );
}
