"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import type { SiteType } from "@/lib/types";

export function SiteTabs({ siteId, siteType }: { siteId: string; siteType: SiteType }) {
  const pathname = usePathname();
  const showUsn = siteType === "ROOFTOP_RESIDENTIAL" || siteType === "ROOFTOP_CI";
  const tabs = [
    { href: `/sites/${siteId}`, label: "Assessment" },
    { href: `/sites/${siteId}/boundary`, label: "Boundary" },
    { href: `/sites/${siteId}/panorama`, label: "Panorama" },
    ...(showUsn ? [{ href: `/sites/${siteId}/usn`, label: "USN" }] : []),
    { href: `/sites/${siteId}/history`, label: "History" },
  ];
  return (
    <nav aria-label="Site sections" className="flex gap-1 overflow-x-auto border-b border-line">
      {tabs.map((tab) => {
        const active = pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "whitespace-nowrap border-b-2 px-3 py-2 text-sm",
              active ? "border-amber font-medium text-ink" : "border-transparent text-ink-soft hover:text-ink"
            )}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
