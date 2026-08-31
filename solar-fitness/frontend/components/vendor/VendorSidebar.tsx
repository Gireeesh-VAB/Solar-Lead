"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ClipboardList,
  Compass,
  LayoutGrid,
  LineChart,
  Sun,
  UserRound,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  {
    group: "Overview",
    items: [{ href: "/vendor/dashboard", label: "Dashboard", icon: LayoutGrid }],
  },
  {
    group: "Work",
    items: [
      { href: "/vendor/jobs", label: "Job queue", icon: ClipboardList },
      { href: "/vendor/submissions", label: "Submissions", icon: ClipboardList },
    ],
  },
  {
    group: "Performance",
    items: [
      { href: "/vendor/earnings", label: "Earnings", icon: Wallet },
      { href: "/vendor/performance", label: "Performance", icon: LineChart },
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
      className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:flex"
      aria-label="Vendor navigation"
    >
      <Link href="/vendor/dashboard" className="flex items-center gap-2 border-b border-line px-4 py-4">
        <Sun size={20} strokeWidth={1.75} className="text-teal" aria-hidden="true" />
        <span className="text-sm font-semibold leading-tight text-ink">
          Solar Site Fitness
          <br />
          <span className="font-normal text-ink-soft">Vendor portal</span>
        </span>
      </Link>
      <div className="flex-1 overflow-y-auto scrollbar-thin py-3">
        {NAV.map((group) => (
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
                        active ? "bg-teal text-white" : "text-ink-soft hover:bg-surface-2 hover:text-ink"
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
