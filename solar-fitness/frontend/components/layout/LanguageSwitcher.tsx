"use client";

// EN / HI toggle for the customer-facing Header — see lib/i18n for the
// underlying dictionary/useT() foundation. Deliberately just two buttons
// (not a select) so it stays a single readable tap-target on mobile,
// matching the rest of the simple-first redesign's plain, big-target style.

import { LANGUAGE_OPTIONS, useT } from "@/lib/i18n/LanguageContext";
import { cn } from "@/lib/utils";

export function LanguageSwitcher() {
  const { t, lang, setLang } = useT();

  return (
    <div
      role="group"
      aria-label={t("nav.language", "Language")}
      className="flex items-center gap-0.5 rounded-[var(--radius-app)] border border-line bg-surface p-0.5"
    >
      {LANGUAGE_OPTIONS.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => setLang(option.value)}
          aria-pressed={lang === option.value}
          className={cn(
            "rounded-[calc(var(--radius-app)-2px)] px-2 py-1 text-xs font-semibold transition-colors",
            lang === option.value ? "bg-brand text-white" : "text-ink-soft hover:text-ink"
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
