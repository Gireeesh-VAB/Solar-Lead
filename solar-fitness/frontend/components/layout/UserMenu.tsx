"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, LogOut, Settings, User } from "lucide-react";
import { cn } from "@/lib/utils";
import { logout } from "@/lib/api/auth";
import { getStoredSession } from "@/lib/auth/session";

type UserMenuProps = {
  /** Fallback shown until the real session loads client-side (and if none is stored). */
  name: string;
  role: string;
  initials: string;
  profileHref?: string;
  settingsHref?: string;
  accentVar?: string;
};

const ROLE_LABEL: Record<string, string> = {
  customer: "Homeowner",
  vendor: "Vendor",
  admin: "Super Admin",
};

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (parts[0]?.[0] ?? "").concat(parts.length > 1 ? parts[parts.length - 1][0] : "").toUpperCase();
}

export function UserMenu({
  name: fallbackName,
  role: fallbackRole,
  initials: fallbackInitials,
  profileHref,
  settingsHref,
  accentVar = "var(--blue)",
}: UserMenuProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const [identity, setIdentity] = useState({ name: fallbackName, role: fallbackRole, initials: fallbackInitials });

  useEffect(() => {
    const session = getStoredSession();
    if (session) {
      setIdentity({
        name: session.name,
        role: ROLE_LABEL[session.role] ?? session.role,
        initials: initialsFor(session.name),
      });
    }
  }, []);
  const { name, role, initials } = identity;

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const signOut = () => {
    setOpen(false);
    logout();
    router.push("/login");
  };

  return (
    <div className="relative border-l border-line pl-3" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-[var(--radius-app)] px-1 py-1 outline-none hover:bg-surface-2 focus-visible:bg-surface-2"
      >
        <span
          className="flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold text-white"
          style={{ background: accentVar }}
          aria-hidden="true"
        >
          {initials}
        </span>
        <span className="hidden text-left sm:block">
          <span className="block text-sm leading-tight text-ink">{name}</span>
          <span className="block text-[11px] leading-tight text-ink-faint">{role}</span>
        </span>
        <ChevronDown size={14} strokeWidth={1.75} className="hidden text-ink-faint sm:block" aria-hidden="true" />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-20 w-56 rounded-[var(--radius-app)] border border-line bg-paper py-1 shadow-[var(--shadow-float)]"
        >
          <div className="border-b border-line px-3 py-2">
            <p className="text-sm font-medium text-ink">{name}</p>
            <p className="text-xs text-ink-faint">{role}</p>
          </div>
          {profileHref && (
            <Link
              href={profileHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-ink-soft hover:bg-surface-2 hover:text-ink"
            >
              <User size={15} strokeWidth={1.75} aria-hidden="true" />
              Profile
            </Link>
          )}
          {settingsHref && (
            <Link
              href={settingsHref}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm text-ink-soft hover:bg-surface-2 hover:text-ink"
            >
              <Settings size={15} strokeWidth={1.75} aria-hidden="true" />
              Settings
            </Link>
          )}
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            className={cn(
              "flex w-full items-center gap-2 px-3 py-2 text-left text-sm outline-none hover:bg-bad-bg",
              "text-bad"
            )}
            style={{ color: "var(--bad)" }}
          >
            <LogOut size={15} strokeWidth={1.75} aria-hidden="true" />
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
