// Theme preference (System / Light / Dark) — client-only by design.
//
// app/globals.css already ships full light/dark CSS token blocks: the
// default `:root` (light), an automatic `@media (prefers-color-scheme:
// dark)` override, and an explicit `:root[data-theme="dark"]` override.
// Nothing previously set that `data-theme` attribute — this module and
// the inline script in app/layout.tsx are the only wiring needed.
//
// Persisted to localStorage, not the backend: unlike vendor notification
// preferences (a cross-device account setting with real backend meaning),
// theme is a per-browser display preference with no server-side concept
// to persist it against.
//
// Deliberately has NO "react" import (see lib/theme-client.ts for the
// useSyncExternalStore-based hook) — app/layout.tsx (a Server Component)
// imports THEME_INIT_SCRIPT from this file, and Next.js poisons a Server
// Component's whole module graph if anything it imports touches a
// client-only React API, even an unused export.

export type ThemePreference = "system" | "light" | "dark";

export const THEME_KEY = "solarfit-theme";

export function readStoredTheme(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const raw = window.localStorage.getItem(THEME_KEY);
    return raw === "light" || raw === "dark" ? raw : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(theme: ThemePreference): void {
  if (typeof document === "undefined") return;
  if (theme === "system") {
    delete document.documentElement.dataset.theme;
  } else {
    document.documentElement.dataset.theme = theme;
  }
}

// Inlined into app/layout.tsx's <head> verbatim (as a string, not
// imported) so it runs before first paint — a React effect would only
// apply the theme after hydration, causing a visible flash of the wrong
// theme on every load for anyone who chose an explicit Light/Dark.
export const THEME_INIT_SCRIPT = `
(function () {
  try {
    var t = window.localStorage.getItem("${THEME_KEY}");
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  } catch (e) {}
})();
`;
