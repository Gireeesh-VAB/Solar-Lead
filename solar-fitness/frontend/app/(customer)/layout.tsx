import Link from "next/link";
import { Home, ListChecks, Sun, User } from "lucide-react";
import { Header } from "@/components/layout/Header";
import { AuthGuard } from "@/components/auth/AuthGuard";

const NAV_ITEMS = [
  { href: "/home", label: "Home", icon: Home },
  { href: "/checks", label: "My Checks", icon: ListChecks },
  { href: "/profile", label: "Profile", icon: User },
];

export default function CustomerLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard role="customer">
    <div className="flex min-h-screen w-full flex-col">
      <Header
        showSearch={false}
        notificationsHref={undefined}
        settingsHref={undefined}
        profileHref="/profile"
        userName="Priya Raman"
        userRole="Homeowner"
        userInitials="PR"
        accentVar="var(--amber)"
        navSlot={
          <>
            <Link href="/home" className="flex items-center gap-2 font-semibold text-ink">
              <Sun size={20} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
              <span className="hidden sm:inline">Solar Check</span>
            </Link>
            <nav className="ml-4 hidden items-center gap-1 md:flex">
              {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
                <Link
                  key={href}
                  href={href}
                  className="flex items-center gap-1.5 rounded-[var(--radius-app)] px-3 py-1.5 text-sm font-medium text-ink-soft hover:bg-surface-2 hover:text-ink"
                >
                  <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
                  {label}
                </Link>
              ))}
            </nav>
          </>
        }
      />
      <main className="flex-1 overflow-x-hidden px-4 pb-24 pt-6 md:px-6 md:pb-6">{children}</main>

      {/* Mobile bottom nav */}
      <nav
        className="fixed inset-x-0 bottom-0 z-20 flex items-center justify-around border-t border-line bg-paper py-1.5 pb-[max(0.375rem,env(safe-area-inset-bottom))] shadow-[var(--shadow-float)] md:hidden"
        aria-label="Primary"
      >
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex flex-1 flex-col items-center gap-0.5 rounded-[var(--radius-app)] py-1.5 text-[11px] font-medium text-ink-soft hover:text-ink"
          >
            <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
    </div>
    </AuthGuard>
  );
}
