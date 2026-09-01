"use client";

// Layout-level guard for the customer/vendor/admin/field portals: redirects
// an unauthenticated visitor to /login, and a signed-in user of the wrong
// role to their own portal's landing page rather than letting them view one
// that isn't theirs.

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
    if (session.role !== role) {
      router.replace(ROLE_LANDING[session.role] ?? "/login");
      return;
    }
    setReady(true);
  }, [role, router]);

  if (!ready) return null;
  return <>{children}</>;
}
