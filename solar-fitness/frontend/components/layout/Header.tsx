import Link from "next/link";
import type { ReactNode } from "react";
import { Bell, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";

export interface HeaderProps {
  /** Show the global search link. Defaults to true (original portfolio behaviour). */
  showSearch?: boolean;
  searchHref?: string;
  searchLabel?: string;
  /** Optional compact nav rendered between the search slot and the user menu (desktop only). */
  navSlot?: ReactNode;
  notificationsHref?: string;
  userName?: string;
  userRole?: string;
  userInitials?: string;
  profileHref?: string;
  settingsHref?: string;
  accentVar?: string;
}

export function Header({
  showSearch = true,
  searchHref = "/search",
  searchLabel = "Search sites, USN, coordinates…",
  navSlot,
  notificationsHref = "/settings/notifications",
  userName = "Demo Analyst",
  userRole = "Customer · Demo Agency",
  userInitials = "DA",
  profileHref = "/settings/organisation",
  settingsHref = "/settings/organisation",
  accentVar = "var(--amber)",
}: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-paper px-4 py-3 md:px-6">
      {showSearch ? (
        <Link
          href={searchHref}
          className="flex max-w-sm flex-1 items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft hover:border-blue"
        >
          <Search size={15} strokeWidth={1.75} aria-hidden="true" />
          {searchLabel}
        </Link>
      ) : (
        <div className="flex flex-1 items-center gap-4">{navSlot}</div>
      )}
      <div className="flex items-center gap-3">
        {showSearch && navSlot}
        {notificationsHref && (
          <Link href={notificationsHref} aria-label="Notifications" className="text-ink-soft hover:text-ink">
            <Bell size={18} strokeWidth={1.75} />
          </Link>
        )}
        <UserMenu
          name={userName}
          role={userRole}
          initials={userInitials}
          profileHref={profileHref}
          settingsHref={settingsHref}
          accentVar={accentVar}
        />
      </div>
    </header>
  );
}
