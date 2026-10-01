"use client";

// Route-based tabs, same pattern as components/sites/SiteTabs.tsx — the
// only tab precedent in this codebase (usePathname()-driven active
// state, plain Links, no client-side tab-switching state).

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { href: "/vendor/profile", label: "Overview" },
  { href: "/vendor/profile/settings", label: "Settings" },
];

export function ProfileTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="Profile sections" className="flex gap-1 overflow-x-auto border-b border-line">
      {TABS.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "whitespace-nowrap border-b-2 px-3 py-2 text-sm",
              active ? "border-brand font-medium text-ink" : "border-transparent text-ink-soft hover:text-ink"
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
