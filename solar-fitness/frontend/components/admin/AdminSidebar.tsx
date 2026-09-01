"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ClipboardList,
  FileBarChart,
  Gauge,
  LayoutGrid,
  ScrollText,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  {
    group: "Overview",
    items: [{ href: "/admin/dashboard", label: "Dashboard", icon: LayoutGrid }],
  },
  {
    group: "Accounts",
    items: [
      { href: "/admin/vendors", label: "Vendors", icon: Users },
      { href: "/admin/vendors/verification", label: "Verification queue", icon: ShieldCheck },
    ],
  },
  {
    group: "Operations",
    items: [{ href: "/admin/assessments", label: "Assessments", icon: ClipboardList }],
  },
  {
    group: "Platform",
    items: [
      { href: "/admin/platform/jurisdictions", label: "Jurisdiction packs", icon: Gauge },
      { href: "/admin/platform/models", label: "Model approval", icon: Gauge },
      { href: "/admin/platform/calibration", label: "Calibration", icon: Gauge },
    ],
  },
  {
    group: "Insights",
    items: [
      { href: "/admin/reports", label: "Reports", icon: FileBarChart },
      { href: "/admin/audit-log", label: "Audit log", icon: ScrollText },
    ],
  },
  {
    group: "System",
    items: [{ href: "/admin/configuration", label: "Configuration", icon: Settings }],
  },
];

export function AdminSidebar() {
  const pathname = usePathname();
  return (
    <nav
      className="hidden w-60 shrink-0 flex-col border-r border-line bg-surface md:flex"
      aria-label="Admin navigation"
    >
      <Link href="/admin/dashboard" className="flex items-center gap-2 border-b border-line px-4 py-4">
        <ShieldCheck size={20} strokeWidth={1.75} className="text-slate" aria-hidden="true" />
        <span className="text-sm font-semibold leading-tight text-ink">
          Solar Site Fitness
          <br />
          <span className="font-normal text-ink-soft">Super admin</span>
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
                        active ? "bg-slate text-white" : "text-ink-soft hover:bg-surface-2 hover:text-ink"
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
