"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Sparkles, Zap, Shield, Clock } from "lucide-react";
import { useScrollReveal } from "@/lib/hooks/useScrollReveal";

const trustItems = [
  { icon: Zap, text: "Instant analysis" },
  { icon: Shield, text: "100% free quote" },
  { icon: Clock, text: "24/7 support" },
];

export default function CTASection() {
  const { ref, inView } = useScrollReveal("-80px");
  return (
    <section className="py-20 lg:py-24">
      <div className="mx-auto max-w-4xl px-4 text-center sm:px-6 lg:px-8">
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.5 }}
        >
          <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-good-bg px-4 py-1.5 text-sm font-semibold text-good">
            <Sparkles className="h-4 w-4" />
            Ready to go green?
          </div>

          <h2 className="mb-5 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Start your <span className="gradient-text">solar journey</span>
          </h2>

          <p className="mx-auto mb-10 max-w-2xl text-lg text-ink-soft">
            Join homeowners who have already made the switch to clean, renewable
            energy — your sustainable future starts with one address.
          </p>

          <Link
            href="/signup"
            className="inline-flex items-center gap-3 rounded-full bg-brand px-8 py-4 text-lg font-semibold text-white shadow-[var(--shadow-float)] transition-colors hover:bg-brand-soft"
          >
            Start your solar journey
            <ArrowRight className="h-5 w-5" />
          </Link>

          <div className="mt-10 flex flex-wrap justify-center gap-x-8 gap-y-3">
            {trustItems.map((item) => (
              <div key={item.text} className="flex items-center gap-2 text-sm font-medium text-ink-soft">
                <item.icon className="h-4 w-4 text-good" />
                {item.text}
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
