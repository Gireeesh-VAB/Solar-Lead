import Link from "next/link";
import { Bell, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";

export function VendorHeader() {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-paper px-4 py-3 md:px-6">
      <Link
        href="/vendor/jobs"
        className="flex max-w-sm flex-1 items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft hover:border-teal"
      >
        <Search size={15} strokeWidth={1.75} aria-hidden="true" />
        Search jobs, sites, districts…
      </Link>
      <div className="flex items-center gap-3">
        <Link href="/vendor/submissions" aria-label="Notifications" className="text-ink-soft hover:text-ink">
          <Bell size={18} strokeWidth={1.75} />
        </Link>
        <UserMenu
          name="Demo Surveyor"
          role="Vendor · Demo Surveyor"
          initials="DS"
          profileHref="/vendor/profile"
          settingsHref="/vendor/service-area"
          accentVar="var(--teal)"
        />
      </div>
    </header>
  );
}
