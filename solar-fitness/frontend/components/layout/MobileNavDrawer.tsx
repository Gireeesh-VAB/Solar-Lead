"use client";

// Admin/vendor portals only ever had a desktop sidebar (`hidden md:flex` —
// completely gone below that breakpoint, see BackButton.tsx's own comment
// on this same gap) with nothing replacing it on mobile: no hamburger, no
// drawer, no bottom nav. A logged-in admin/vendor on a phone could reach
// Dashboard and had no way to get anywhere else short of typing a URL.
// This is that replacement — a slide-out drawer reusing the exact same
// grouped nav data each portal's own desktop Sidebar already defines, so
// the two navs can never drift apart.

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Menu, X, type LucideIcon } from "lucide-react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface MobileNavGroup {
  group: string;
  items: { href: string; label: string; icon: LucideIcon }[];
}

export function MobileNavDrawer({
  title,
  subtitle,
  icon: BrandIcon,
  groups,
}: {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  groups: MobileNavGroup[];
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // Route change is the normal way a drawer nav closes — same as tapping
  // a link, just also covers back/forward navigation. Adjusted during
  // render (React's own recommended pattern for "reset state when a
  // prop changes") rather than in an effect, which would cost an extra
  // render pass for no benefit here.
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setOpen(false);
  }

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const { overflow } = document.body.style;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open navigation menu"
        aria-expanded={open}
        className="flex md:hidden shrink-0 min-h-[44px] min-w-[44px] items-center justify-center rounded-[var(--radius-app)] text-ink-soft transition-colors hover:bg-surface-2 hover:text-ink active:bg-surface-2"
      >
        <Menu size={20} strokeWidth={1.75} aria-hidden="true" />
      </button>

      <AnimatePresence>
        {open && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="fixed inset-0 z-40 bg-black/40 md:hidden"
              onClick={() => setOpen(false)}
              aria-hidden="true"
            />
            <motion.nav
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col bg-surface shadow-[var(--shadow-float)] md:hidden"
              aria-label="Navigation"
            >
              <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-4">
                <div className="flex items-center gap-2">
                  <BrandIcon size={20} strokeWidth={1.75} className="text-slate" aria-hidden="true" />
                  <span className="text-sm font-semibold leading-tight text-ink">
                    {title}
                    <br />
                    <span className="font-normal text-ink-soft">{subtitle}</span>
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation menu"
                  className="flex min-h-[44px] min-w-[44px] items-center justify-center rounded-[var(--radius-app)] text-ink-soft hover:bg-surface-2 hover:text-ink"
                >
                  <X size={18} strokeWidth={1.75} aria-hidden="true" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto scrollbar-thin py-3">
                {groups.map((g) => (
                  <div key={g.group} className="mb-4 px-3">
                    <p className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
                      {g.group}
                    </p>
                    <ul className="space-y-0.5">
                      {g.items.map((item) => {
                        const active = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                          <li key={item.href}>
                            <Link
                              href={item.href}
                              aria-current={active ? "page" : undefined}
                              className={cn(
                                "flex items-center gap-2 rounded-[var(--radius-app)] px-2 py-2 text-sm",
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
            </motion.nav>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
