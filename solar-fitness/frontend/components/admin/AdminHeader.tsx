"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";
import { useAdminVendors } from "@/lib/query/hooks";

function VendorSearch() {
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedQ(q), 250);
    return () => clearTimeout(id);
  }, [q]);

  const hasQuery = debouncedQ.trim().length > 0;
  const results = useAdminVendors({ q: debouncedQ.trim() }, { enabled: hasQuery });
  const matches = hasQuery ? (results.data ?? []).slice(0, 6) : [];

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={containerRef} className="relative max-w-sm flex-1">
      <div className="flex items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-1.5 text-sm text-ink-soft focus-within:border-slate">
        <Search size={15} strokeWidth={1.75} aria-hidden="true" />
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder="Search vendors…"
          aria-label="Search vendors"
          className="w-full bg-transparent text-ink outline-none placeholder:text-ink-soft"
        />
      </div>
      {open && debouncedQ.trim().length > 0 && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-72 overflow-y-auto rounded-[var(--radius-app)] border border-line bg-paper shadow-[var(--shadow-float)]">
          {matches.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-soft">No vendors match &ldquo;{debouncedQ}&rdquo;.</p>
          ) : (
            <ul>
              {matches.map((v) => (
                <li key={v.id}>
                  <Link
                    href={`/admin/vendors/${v.id}`}
                    onClick={() => setOpen(false)}
                    className="block px-3 py-2 text-sm text-ink hover:bg-surface"
                  >
                    <span className="font-medium">{v.name}</span>
                    <span className="ml-2 text-xs text-ink-faint">{v.serviceArea}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function AdminHeader() {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-line bg-paper px-4 py-3 md:px-6">
      <VendorSearch />
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
