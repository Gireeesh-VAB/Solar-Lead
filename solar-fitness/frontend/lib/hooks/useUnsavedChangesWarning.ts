"use client";

import { useEffect } from "react";

// Warns on tab-close/refresh only. Next.js App Router has no built-in
// hook for intercepting in-app <Link> navigation (no router-level guard
// like the old Pages Router's routeChangeStart) — building a global
// route-interception wrapper for one form is out of proportion to what
// this is for, so that case is knowingly left unhandled.
export function useUnsavedChangesWarning(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);
}
