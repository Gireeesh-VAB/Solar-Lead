"use client";

// Tracks whether THIS BROWSER TAB has made at least one client-side
// in-app navigation since the module first loaded — the signal
// components/ui/BackButton.tsx needs to decide between router.back()
// (a real previous page exists) and a hardcoded fallback (the user
// landed here directly: a fresh load, a bookmark, a shared deep link —
// browser history here is either empty or points off-site).
//
// Same module-level-external-store shape as lib/theme-client.ts's own
// comment describes: a useEffect that calls React's OWN setState
// directly trips react-hooks/set-state-in-effect (cascading renders),
// and mutating a ref or a plain module variable DURING render trips the
// React Compiler's purity rules (react-hooks/refs, react-hooks/globals)
// this project's eslint config enforces. useSyncExternalStore sidesteps
// both: the effect below only ever calls markNavigated(), a plain
// external mutator, never a React state setter — the actual re-render
// flows through React's own (compiler-safe) subscription plumbing.
import { usePathname } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";

let hasNavigatedThisSession = false;
let lastSeenPathname: string | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): boolean {
  return hasNavigatedThisSession;
}

function getServerSnapshot(): boolean {
  return false;
}

function markNavigated(): void {
  if (hasNavigatedThisSession) return;
  hasNavigatedThisSession = true;
  listeners.forEach((listener) => listener());
}

export function useCanGoBack(): boolean {
  const pathname = usePathname();
  const canGoBack = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  useEffect(() => {
    if (lastSeenPathname !== null && lastSeenPathname !== pathname) {
      markNavigated();
    }
    lastSeenPathname = pathname;
  }, [pathname]);

  return canGoBack;
}
