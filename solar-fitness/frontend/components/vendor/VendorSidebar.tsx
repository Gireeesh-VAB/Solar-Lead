"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ClipboardList, Compass, HardHat, LayoutGrid, Sun, UserRound } from "lucide-react";
import { cn } from "@/lib/utils";

// Exported so MobileNavDrawer (rendered in VendorHeader) reuses the exact
// same nav tree — one source of truth, never two lists that can drift.
export const VENDOR_NAV = [
  {
    group: "Overview",
    items: [{ href: "/vendor/dashboard", label: "Dashboard", icon: LayoutGrid }],
  },
  {
    group: "Work",
    items: [
      { href: "/vendor/jobs", label: "Job queue", icon: ClipboardList },
      { href: "/vendor/installations", label: "Installations", icon: HardHat },
      { href: "/vendor/submissions", label: "Submissions", icon: ClipboardList },
    ],
  },
  {
    group: "Account",
    items: [
      { href: "/vendor/service-area", label: "Service area", icon: Compass },
      { href: "/vendor/profile", label: "Profile", icon: UserRound },
    ],
  },
];

export function VendorSidebar() {
  const pathname = usePathname();
  return (
    <nav
      className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:sticky md:top-0 md:flex md:h-screen"
      aria-label="Vendor navigation"
    >
      <Link href="/vendor/dashboard" className="flex items-center gap-2 border-b border-line px-4 py-4">
        <Sun size={20} strokeWidth={1.75} className="text-brand" aria-hidden="true" />
        <span className="text-sm font-semibold leading-tight text-ink">
          Solar Site Fitness
          <br />
          <span className="font-normal text-ink-soft">Vendor portal</span>
        </span>
      </Link>
      <div className="flex-1 overflow-y-auto scrollbar-thin py-3">
        {VENDOR_NAV.map((group) => (
          <div key={group.group} className="mb-4 px-3">
            <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{group.group}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = pathname === item.href || pathname.startsWith(item.href + "/");
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-sm",
                        active ? "bg-brand text-white" : "text-ink-soft hover:bg-surface-2 hover:text-ink"
                      )}
                    >
                      <item.icon size={15} strokeWidth={1.75} aria-hidden="true" />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}
