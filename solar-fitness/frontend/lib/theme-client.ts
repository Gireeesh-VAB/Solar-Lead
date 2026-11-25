"use client";

// useThemePreference()/setTheme() — split out of lib/theme.ts because
// useSyncExternalStore is a client-only React API, and app/layout.tsx (a
// Server Component) needs to import lib/theme.ts's THEME_INIT_SCRIPT
// without pulling this in.

import { useSyncExternalStore } from "react";
import { applyTheme, readStoredTheme, THEME_KEY, type ThemePreference } from "@/lib/theme";

// Same module-level-external-store shape as lib/i18n/LanguageContext.tsx's
// readStoredLang()/getSnapshot() — useState+useEffect(setState) here would
// trip react-hooks/set-state-in-effect (an extra cascading render); this
// gives the same "read once, hydration-safe" result without it.
let currentTheme: ThemePreference = "system";
let hydratedFromStorage = false;
const listeners = new Set<() => void>();

function getSnapshot(): ThemePreference {
  if (!hydratedFromStorage && typeof window !== "undefined") {
    hydratedFromStorage = true;
    currentTheme = readStoredTheme();
  }
  return currentTheme;
}

function getServerSnapshot(): ThemePreference {
  return "system";
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function setTheme(theme: ThemePreference): void {
  hydratedFromStorage = true;
  currentTheme = theme;
  try {
    if (theme === "system") {
      window.localStorage.removeItem(THEME_KEY);
    } else {
      window.localStorage.setItem(THEME_KEY, theme);
    }
  } catch {
    // Storage unavailable — the attribute below still applies for this load.
  }
  applyTheme(theme);
  listeners.forEach((listener) => listener());
}

/** The Appearance section's source of truth — hydration-safe (always
 * "system" on the server/first paint, the real stored value once
 * mounted). */
export function useThemePreference(): ThemePreference {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export type { ThemePreference };
