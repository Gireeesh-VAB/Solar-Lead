"use client";

// Layout-level guard for the customer/vendor/admin/field portals: redirects
// an unauthenticated visitor to /login, and a signed-in user of the wrong
// role to their own portal's landing page rather than letting them view one
// that isn't theirs.
//
// One deliberate exception: an admin session is let through the CUSTOMER
// layout specifically (never the vendor one — not asked for, not needed).
// This is what lets the admin assessment-review page's "Feasibility"
// button open the exact same result page a customer sees, in a real,
// working way — the backend side of this (routers/app_checks.py::
// _readable_check_or_404()) already grants admin read access to every
// endpoint that page depends on; this is the matching frontend half.
// Still customer-only for a vendor/customer viewing the admin or vendor
// layout — this widens exactly one direction, not every combination.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getStoredSession, ROLE_LANDING, type PortalRole } from "@/lib/auth/session";

export function AuthGuard({ role, children }: { role: PortalRole; children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const session = getStoredSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    const allowed = session.role === role || (session.role === "admin" && role === "customer");
    if (!allowed) {
      router.replace(ROLE_LANDING[session.role] ?? "/login");
      return;
    }
    setReady(true);
  }, [role, router]);

  if (!ready) return null;
  return <>{children}</>;
}
