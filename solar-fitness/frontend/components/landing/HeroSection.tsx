"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { MapPin, Satellite, Calculator, Sun, Zap, Check, Sparkles } from "lucide-react";

const stages = [
  { title: "Enter your address", description: "Type your address to begin", icon: MapPin },
  { title: "Satellite imagery", description: "We fetch a high-res view of your rooftop", icon: Satellite },
  { title: "AI analysis", description: "We calculate dimensions and solar feasibility", icon: Calculator },
  { title: "3D panel design", description: "Get a rooftop design with optimal panel placement", icon: Sun },
];

export default function HeroSection() {
  const router = useRouter();
  const [address, setAddress] = useState("");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    // Analysis requires an account (see the (customer)/check/new route's
    // AuthGuard) — there's no mechanism yet to carry the typed address
    // through signup, so this sends the visitor to sign up rather than
    // silently dropping what they typed on a dead-end page.
    router.push("/signup");
  }

  return (
    <section className="relative overflow-hidden bg-paper pb-16 pt-28 lg:pb-24 lg:pt-36">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,color-mix(in_srgb,var(--brand)_6%,transparent)_1px,transparent_1px),linear-gradient(to_bottom,color-mix(in_srgb,var(--brand)_6%,transparent)_1px,transparent_1px)] bg-[size:56px_56px] [mask-image:radial-gradient(ellipse_70%_60%_at_50%_0%,black,transparent)]"
      />

      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="grid items-center gap-14 lg:grid-cols-2 lg:gap-16">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="text-center lg:text-left"
          >
            <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-good-bg px-4 py-1.5 text-sm font-medium text-good">
              <Sparkles className="h-4 w-4" />
              AI-powered solar analysis
            </div>

            <h1 className="mb-5 text-4xl font-bold leading-[1.1] tracking-tight text-ink sm:text-5xl lg:text-6xl">
              Turn your <span className="gradient-text">rooftop</span>
              <br />
              into a powerhouse
            </h1>

            <p className="mx-auto mb-8 max-w-xl text-lg leading-relaxed text-ink-soft lg:mx-0">
              Enter your address and see your roof&apos;s solar potential — satellite
              analysis, capacity, and estimated savings, in one report.
            </p>

            <form onSubmit={handleSubmit} className="mx-auto max-w-xl lg:mx-0">
              <div className="flex items-center gap-2 rounded-2xl border border-line bg-surface p-2 shadow-[var(--shadow-float)] transition-colors focus-within:border-brand">
                <MapPin className="ml-2 h-5 w-5 flex-shrink-0 text-ink-faint" />
                <input
                  type="text"
                  value={address}
                  onChange={(e) => setAddress(e.target.value)}
                  placeholder="Enter your address…"
                  className="min-w-0 flex-1 bg-transparent py-2 text-base text-ink outline-none placeholder:text-ink-faint"
                />
                <button
                  type="submit"
                  className="inline-flex flex-shrink-0 items-center gap-2 rounded-xl bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-soft"
                >
                  <span className="hidden sm:inline">Analyze</span>
                  <Zap className="h-4 w-4" />
                </button>
              </div>
              <p className="mt-3 flex items-center justify-center gap-1.5 text-sm text-ink-soft lg:justify-start">
                <Check className="h-4 w-4 text-good" />
                Free instant analysis · No credit card required
              </p>
            </form>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="rounded-3xl border border-line bg-surface p-6 shadow-[var(--shadow-float)] sm:p-8"
          >
            <p className="mb-5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              How it works
            </p>
            <ol className="space-y-5">
              {stages.map((stage, index) => (
                <li key={stage.title} className="flex items-start gap-4">
                  <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-good-bg text-good">
                    <stage.icon className="h-5 w-5" strokeWidth={1.75} />
                  </div>
                  <div className="min-w-0 flex-1 border-b border-line pb-5 last:border-none last:pb-0">
                    <div className="flex items-center gap-2">
                      <span className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-surface-2 font-mono text-[11px] font-semibold text-ink-soft">
                        {index + 1}
                      </span>
                      <p className="font-semibold text-ink">{stage.title}</p>
                    </div>
                    <p className="mt-1 text-sm text-ink-soft">{stage.description}</p>
                  </div>
                </li>
              ))}
            </ol>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
