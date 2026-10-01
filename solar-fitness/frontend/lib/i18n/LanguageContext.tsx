"use client";

// Minimal multi-language foundation for the CUSTOMER-facing flow only.
// Deliberately small: two flat/nested dictionaries (en, hi), a
// localStorage-backed language choice, and a useT() hook that never
// throws and never renders `undefined` — it falls back English-first,
// then to a caller-supplied fallback, then to a visibly-marked key so a
// missing translation is obvious in testing rather than silently blank.
//
// Vendor/admin screens intentionally never import this — see the Phase 4
// plan (clever-orbiting-glade.md) for why this stays customer-only.

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import en from "./dictionaries/en.json";
import hi from "./dictionaries/hi.json";

export type Lang = "en" | "hi";

const STORAGE_KEY = "solarfit-lang";
const DEFAULT_LANG: Lang = "en";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const DICTIONARIES: Record<Lang, any> = { en, hi };

export const LANGUAGE_OPTIONS: { value: Lang; label: string }[] = [
  { value: "en", label: "EN" },
  { value: "hi", label: "HI" },
];

function readStoredLang(): Lang {
  if (typeof window === "undefined") return DEFAULT_LANG;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return stored === "hi" ? "hi" : DEFAULT_LANG;
  } catch {
    // localStorage can throw (private mode, disabled storage, etc.) —
    // fall back to English rather than crashing the page.
    return DEFAULT_LANG;
  }
}

// A tiny module-level external store, read via useSyncExternalStore rather
// than "useState + useEffect(setState)" — the latter trips
// react-hooks/set-state-in-effect and causes an extra cascading render.
// getServerSnapshot always returns English so SSR/first-paint markup
// matches, exactly like the old effect-based approach did, but without
// the lint violation or the extra render.
let currentLang: Lang = DEFAULT_LANG;
let hydratedFromStorage = false;
const listeners = new Set<() => void>();

function getSnapshot(): Lang {
  if (!hydratedFromStorage && typeof window !== "undefined") {
    hydratedFromStorage = true;
    currentLang = readStoredLang();
  }
  return currentLang;
}

function getServerSnapshot(): Lang {
  return DEFAULT_LANG;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function setStoredLang(next: Lang): void {
  hydratedFromStorage = true;
  currentLang = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Ignore — the in-memory language still updates for this session.
  }
  listeners.forEach((listener) => listener());
}

interface LanguageContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const lang = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const setLang = useCallback((next: Lang) => setStoredLang(next), []);
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

/** Reads the active language + setter. Falls back to English-only,
 *  no-op-setter behaviour if used outside a LanguageProvider, rather than
 *  throwing — so a stray import never crashes an unrelated screen. */
export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext);
  if (ctx) return ctx;
  return { lang: DEFAULT_LANG, setLang: () => {} };
}

function lookup(dict: unknown, key: string): string | undefined {
  const value = key.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, dict);
  return typeof value === "string" ? value : undefined;
}

function interpolate(template: string, vars?: Record<string, string | number>): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in vars ? String(vars[name]) : match
  );
}

/** t(key, fallback?, vars?) — looks up `key` (dot-path into the active
 *  dictionary) in the active language, falls back to English, then to
 *  `fallback` if given, then to a clearly-marked `[key]` string so a
 *  missing translation is never silently rendered as `undefined` or a
 *  raw untranslated-looking key. Never throws. */
export function useT() {
  const { lang, setLang } = useLanguage();

  const t = useCallback(
    (key: string, fallback?: string, vars?: Record<string, string | number>): string => {
      const active = lookup(DICTIONARIES[lang], key);
      if (active != null) return interpolate(active, vars);

      if (lang !== "en") {
        const english = lookup(DICTIONARIES.en, key);
        if (english != null) return interpolate(english, vars);
      }

      if (fallback != null) return interpolate(fallback, vars);

      return `[${key}]`;
    },
    [lang]
  );

  return { t, lang, setLang };
}
