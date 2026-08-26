import Link from "next/link";
import { Bell, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";

export function AdminHeader() {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-paper px-4 py-3 md:px-6">
      <Link
        href="/admin/tenants"
        className="flex max-w-sm flex-1 items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft hover:border-slate"
      >
        <Search size={15} strokeWidth={1.75} aria-hidden="true" />
        Search tenants, vendors, sites…
      </Link>
      <div className="flex items-center gap-3">
        <Link href="/admin/audit-log" aria-label="Notifications" className="text-ink-soft hover:text-ink">
          <Bell size={18} strokeWidth={1.75} />
        </Link>
        <UserMenu
          name="Demo Admin"
          role="Super Admin · Platform Team"
          initials="SA"
          profileHref="/admin/configuration"
          settingsHref="/admin/configuration"
          accentVar="var(--slate)"
        />
      </div>
    </header>
  );
}
