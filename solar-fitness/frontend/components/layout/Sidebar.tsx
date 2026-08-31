"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Building2,
  FileBarChart2,
  FolderInput,
  LayoutGrid,
  Search,
  Settings,
  Sun,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  {
    group: "Portfolio",
    items: [
      { href: "/portfolio", label: "Overview", icon: LayoutGrid },
      { href: "/portfolio/map", label: "Map", icon: LayoutGrid },
      { href: "/portfolio/compare", label: "Compare", icon: LayoutGrid },
    ],
  },
  {
    group: "Sites",
    items: [
      { href: "/sites", label: "All sites", icon: Building2 },
      { href: "/sites/new", label: "New site", icon: Building2 },
      { href: "/sites/composite/new", label: "New composite", icon: Building2 },
    ],
  },
  {
    group: "Data",
    items: [
      { href: "/imports", label: "Bulk imports", icon: FolderInput },
      { href: "/search", label: "Search", icon: Search },
    ],
  },
  {
    group: "Reports",
    items: [
      { href: "/reports/export", label: "Export", icon: FileBarChart2 },
      { href: "/reports/calibration", label: "Calibration", icon: FileBarChart2 },
      { href: "/reports/disclosure", label: "Disclosure", icon: FileBarChart2 },
    ],
  },
  {
    group: "Settings",
    items: [
      { href: "/settings/organisation", label: "Organisation", icon: Settings },
      { href: "/settings/jurisdictions", label: "Jurisdictions", icon: Settings },
      { href: "/settings/models", label: "Model versions", icon: Settings },
      { href: "/settings/api-keys", label: "API keys", icon: Settings },
      { href: "/settings/notifications", label: "Notifications", icon: Settings },
      { href: "/settings/billing", label: "Billing", icon: Settings },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <nav
      className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:flex"
      aria-label="Main navigation"
    >
      <Link href="/portfolio" className="flex items-center gap-2 border-b border-line px-4 py-4">
        <Sun size={20} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
        <span className="text-sm font-semibold leading-tight text-ink">
          Solar Site Fitness
          <br />
          <span className="font-normal text-ink-soft">&amp; Capacity Engine</span>
        </span>
      </Link>
      <div className="flex-1 overflow-y-auto scrollbar-thin py-3">
        {NAV.map((group) => (
          <div key={group.group} className="mb-4 px-3">
            <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{group.group}</p>
            <ul className="space-y-0.5">
              {group.items.map((item) => {
                const active = pathname === item.href || (item.href !== "/portfolio" && pathname.startsWith(item.href));
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-sm",
                        active ? "bg-amber text-white" : "text-ink-soft hover:bg-surface-2 hover:text-ink"
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
