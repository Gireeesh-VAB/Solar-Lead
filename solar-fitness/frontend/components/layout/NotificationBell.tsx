"use client";

import { useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { useMarkNotificationRead, useNotifications } from "@/lib/query/hooks";
import { formatDateTime } from "@/lib/utils";

export function NotificationBell() {
  const notifications = useNotifications();
  const markRead = useMarkNotificationRead();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const items = notifications.data ?? [];
  const unreadCount = items.filter((n) => !n.readAt).length;

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
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Notifications"
        className="relative text-ink-soft hover:text-ink"
      >
        <Bell size={18} strokeWidth={1.75} />
        {unreadCount > 0 && (
          <span
            className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-medium text-white"
            style={{ backgroundColor: "var(--bad)" }}
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-80 max-h-96 overflow-y-auto rounded-[var(--radius-app)] border border-line bg-paper shadow-[var(--shadow-float)]">
          {items.length === 0 ? (
            <p className="px-3 py-3 text-sm text-ink-soft">No notifications yet.</p>
          ) : (
            <ul className="divide-y divide-line">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => {
                      if (!n.readAt) markRead.mutate(n.id);
                    }}
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-surface"
                  >
                    <p className={n.readAt ? "text-ink-soft" : "font-medium text-ink"}>{n.title}</p>
                    {n.body && <p className="mt-0.5 text-xs text-ink-faint">{n.body}</p>}
                    <p className="mt-0.5 font-mono tabular text-[10px] text-ink-faint">
                      {formatDateTime(n.createdAt)}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
