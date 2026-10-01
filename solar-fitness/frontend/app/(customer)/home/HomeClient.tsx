"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  ChevronRight,
  Compass,
  Gauge,
  ListChecks,
  ShieldCheck,
  Sparkles,
  SunMedium,
  User,
  Zap,
} from "lucide-react";
import type { Site } from "@/lib/types";
import { formatKwp } from "@/lib/utils";
import { useT } from "@/lib/i18n/LanguageContext";
import { CheckCard } from "../_components/CheckCard";

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

const QUICK_ACTIONS = [
  {
    href: "/check/start",
    labelKey: "home.quickActionNewCheckLabel",
    labelFallback: "New check",
    descriptionKey: "home.quickActionNewCheckDescription",
    descriptionFallback: "Analyze a new roof",
    icon: Compass,
    accent: "var(--brand)",
    accentBg: "var(--good-bg)",
  },
  {
    href: "/checks",
    labelKey: "home.quickActionMyChecksLabel",
    labelFallback: "My checks",
    descriptionKey: "home.quickActionMyChecksDescription",
    descriptionFallback: "See past results",
    icon: ListChecks,
    accent: "var(--blue)",
    accentBg: "var(--surface-2)",
  },
  {
    href: "/profile",
    labelKey: "home.quickActionProfileLabel",
    labelFallback: "Profile",
    descriptionKey: "home.quickActionProfileDescription",
    descriptionFallback: "Account & settings",
    icon: User,
    accent: "var(--teal)",
    accentBg: "var(--surface-2)",
  },
] as const;

export function HomeClient({ checks }: { checks: Site[] }) {
  const { t } = useT();
  const recent = checks.slice(0, 3);
  const suitable = checks.filter((c) => c.latestAssessment?.verdict === "SUITABLE").length;
  const totalKwp = checks.reduce((sum, c) => sum + (c.latestAssessment?.capacityKwp ?? 0), 0);

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={stagger}
      className="mx-auto flex max-w-xl flex-col gap-8"
    >
      {/* ---------- Hero ---------- */}
      <motion.section
        variants={fadeUp}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative isolate overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface px-6 py-11 text-center sm:px-10 sm:py-14"
      >
        {/* ambient backdrop */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute inset-0 opacity-[0.05]"
            style={{
              backgroundImage:
                "linear-gradient(to right, var(--ink) 1px, transparent 1px), linear-gradient(to bottom, var(--ink) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />
          <motion.div
            animate={{ x: [0, 24, 0], y: [0, -16, 0] }}
            transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -top-20 left-1/2 h-64 w-[28rem] -translate-x-1/2 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--amber-soft), transparent 70%)", opacity: 0.55 }}
          />
          <motion.div
            animate={{ x: [0, -20, 0], y: [0, 14, 0] }}
            transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -bottom-24 right-0 h-56 w-72 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--blue-soft), transparent 70%)", opacity: 0.3 }}
          />
        </div>

        <motion.span
          variants={fadeUp}
          className="mx-auto mb-5 inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-wide"
          style={{
            color: "var(--brand)",
            borderColor: "color-mix(in srgb, var(--brand) 30%, transparent)",
            background: "color-mix(in srgb, var(--brand) 8%, transparent)",
          }}
        >
          <Sparkles size={12} strokeWidth={2} aria-hidden="true" />
          {t("home.badge", "Instant rooftop analysis")}
        </motion.span>

        <motion.div
          variants={fadeUp}
          className="relative mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border"
          style={{
            background: "linear-gradient(150deg, var(--warn-bg), var(--surface-2))",
            color: "var(--amber)",
            borderColor: "color-mix(in srgb, var(--amber) 25%, transparent)",
            boxShadow: "var(--shadow-float)",
          }}
        >
          <motion.span
            aria-hidden="true"
            className="absolute inset-0 rounded-full"
            style={{ boxShadow: "0 0 0 0 color-mix(in srgb, var(--amber) 45%, transparent)" }}
            animate={{
              boxShadow: [
                "0 0 0 0 color-mix(in srgb, var(--amber) 35%, transparent)",
                "0 0 0 10px color-mix(in srgb, var(--amber) 0%, transparent)",
              ],
            }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeOut" }}
          />
          <SunMedium size={30} strokeWidth={1.6} aria-hidden="true" />
        </motion.div>

        <motion.h1 variants={fadeUp} className="text-2xl font-semibold tracking-tight text-ink sm:text-[1.75rem]">
          {t("home.heroTitle", "Check your rooftop for solar")}
        </motion.h1>
        <motion.p variants={fadeUp} className="mx-auto mt-2.5 max-w-sm text-sm leading-relaxed text-ink-soft">
          {t(
            "home.heroSubtitle",
            "Point us at a location and we'll tell you whether solar works there — usually in under a minute."
          )}
        </motion.p>

        <motion.div variants={fadeUp} className="mt-6">
          <Link href="/check/start" className="group inline-block">
            <span
              className="inline-flex items-center gap-2 rounded-[var(--radius-app)] px-6 py-2.5 text-sm font-medium text-white transition-all duration-200 group-hover:-translate-y-0.5"
              style={{ background: "linear-gradient(135deg, var(--brand), var(--brand-soft))", boxShadow: "var(--shadow-float)" }}
            >
              {t("home.heroCta", "Check a new location")}
              <ArrowRight size={15} strokeWidth={2} className="transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
            </span>
          </Link>
        </motion.div>

        <motion.p variants={fadeUp} className="mt-4 flex items-center justify-center gap-1.5 text-xs text-ink-faint">
          <ShieldCheck size={13} strokeWidth={1.75} aria-hidden="true" />
          {t("home.heroFootnote", "Free · No site visit needed")}
        </motion.p>
      </motion.section>

      {/* ---------- Quick actions ---------- */}
      <motion.div variants={fadeUp} className="grid grid-cols-3 gap-2.5 sm:gap-3">
        {QUICK_ACTIONS.map(
          ({ href, labelKey, labelFallback, descriptionKey, descriptionFallback, icon: Icon, accent, accentBg }) => (
            <Link key={href} href={href} className="group">
              <div className="flex h-full flex-col items-center gap-2 rounded-[var(--radius-app)] border border-line bg-surface px-2 py-4 text-center transition-all duration-200 group-hover:-translate-y-0.5 group-hover:border-line group-hover:shadow-[var(--shadow-float)] sm:items-start sm:text-left">
                <span
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-transform duration-200 group-hover:scale-105"
                  style={{ background: accentBg, color: accent }}
                  aria-hidden="true"
                >
                  <Icon size={16} strokeWidth={1.75} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-xs font-semibold text-ink">{t(labelKey, labelFallback)}</p>
                  <p className="hidden truncate text-[11px] text-ink-faint sm:block">
                    {t(descriptionKey, descriptionFallback)}
                  </p>
                </div>
              </div>
            </Link>
          )
        )}
      </motion.div>

      {/* ---------- Stats ---------- */}
      {checks.length > 0 && (
        <motion.div variants={fadeUp} className="grid grid-cols-2 gap-3">
          <div className="relative overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface p-4">
            <div aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5" style={{ background: "linear-gradient(90deg, var(--good), transparent)" }} />
            <div className="flex items-center gap-3">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--good-bg)", color: "var(--good)" }}
                aria-hidden="true"
              >
                <Gauge size={16} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <p className="text-lg font-semibold leading-tight text-ink">{suitable}</p>
                <p className="truncate text-xs text-ink-faint">{t("home.statSuitableSites", "Solar-suitable sites")}</p>
              </div>
            </div>
          </div>
          <div className="relative overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface p-4">
            <div aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5" style={{ background: "linear-gradient(90deg, var(--amber), transparent)" }} />
            <div className="flex items-center gap-3">
              <span
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                style={{ background: "var(--warn-bg)", color: "var(--amber)" }}
                aria-hidden="true"
              >
                <Zap size={16} strokeWidth={1.75} />
              </span>
              <div className="min-w-0">
                <p className="text-lg font-semibold leading-tight text-ink">{formatKwp(totalKwp)}</p>
                <p className="truncate text-xs text-ink-faint">{t("home.statPotentialCapacity", "Potential capacity")}</p>
              </div>
            </div>
          </div>
        </motion.div>
      )}

      {/* ---------- Recent checks ---------- */}
      {recent.length > 0 ? (
        <motion.div variants={fadeUp}>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              {t("home.recentChecksTitle", "Recent checks")}
            </h2>
            <Link href="/checks" className="group inline-flex items-center gap-0.5 text-xs font-medium text-blue">
              <span className="group-hover:underline">{t("home.recentChecksViewAll", "View all")}</span>
              <ChevronRight size={13} strokeWidth={2} className="transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden="true" />
            </Link>
          </div>
          <motion.div variants={stagger} className="space-y-2">
            {recent.map((check) => (
              <motion.div key={check.id} variants={fadeUp}>
                <CheckCard check={check} />
              </motion.div>
            ))}
          </motion.div>
        </motion.div>
      ) : (
        <motion.div
          variants={fadeUp}
          className="flex flex-col items-center gap-1.5 rounded-[var(--radius-app)] border border-dashed border-line px-6 py-10 text-center"
        >
          <p className="text-sm font-medium text-ink">{t("home.emptyChecksTitle", "No checks yet")}</p>
          <p className="max-w-xs text-xs text-ink-faint">
            {t(
              "home.emptyChecksDescription",
              "Your first rooftop check will show up here with its suitability score and system size."
            )}
          </p>
        </motion.div>
      )}
    </motion.div>
  );
}
