"use client";

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import {
  Satellite,
  Brain,
  Ruler,
  Palette,
  BarChart3,
  ShieldCheck,
  Leaf,
  Coins,
  Sun,
  Zap,
  Clock,
  HeadphonesIcon,
} from "lucide-react";
import { useScrollReveal } from "@/lib/hooks/useScrollReveal";

// Scroll-reveal for a single grid card — a file-local component (not
// exported/shared) purely because useScrollReveal is a hook and can't be
// called inside the .map() callbacks below; each card still triggers its
// own reveal independently, same as before.
function RevealCard({
  delay,
  className,
  children,
}: {
  delay: number;
  className?: string;
  children: ReactNode;
}) {
  const { ref, inView } = useScrollReveal("-60px");
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 16 }}
      animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
      transition={{ duration: 0.4, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

const features = [
  {
    icon: Satellite,
    title: "Satellite imagery analysis",
    description: "High-resolution satellite imagery to accurately map your rooftop's dimensions and orientation.",
  },
  {
    icon: Brain,
    title: "AI-powered feasibility",
    description: "Advanced analysis of solar potential, accounting for shading, roof angle, and local weather.",
  },
  {
    icon: Ruler,
    title: "Precise measurements",
    description: "Accurate roof dimensions and available space for optimal panel placement.",
  },
  {
    icon: Palette,
    title: "3D design visualization",
    description: "A realistic 3D model of your roof with solar panels before making any commitment.",
  },
  {
    icon: BarChart3,
    title: "Energy production estimates",
    description: "Detailed projections of energy generation, savings, and return on investment over time.",
  },
  {
    icon: ShieldCheck,
    title: "Verified vendors only",
    description: "Connect with pre-screened, certified solar installers with a proven track record.",
  },
];

const benefits = [
  { icon: Leaf, value: "100%", subtitle: "Clean energy" },
  { icon: Coins, value: "30%", subtitle: "Tax credits" },
  { icon: Sun, value: "25+", subtitle: "Years warranty" },
  { icon: Zap, value: "80%", subtitle: "Bill reduction" },
];

const infoCards = [
  { icon: Clock, title: "Quick setup", description: "Get your solar analysis in under 2 minutes. No appointments, no waiting." },
  { icon: HeadphonesIcon, title: "Expert support", description: "Our team of solar experts is available to answer your questions." },
  { icon: ShieldCheck, title: "Satisfaction guaranteed", description: "Not happy with your quote? We'll help you find the right fit." },
];

export default function FeaturesSection() {
  const { ref: headerRef, inView: headerInView } = useScrollReveal("-80px");
  const { ref: benefitsRef, inView: benefitsInView } = useScrollReveal("-80px");

  return (
    <section id="how-it-works" className="bg-paper py-20 lg:py-24">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <motion.div
          ref={headerRef}
          initial={{ opacity: 0, y: 16 }}
          animate={headerInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.5 }}
          className="mx-auto mb-14 max-w-2xl text-center"
        >
          <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-good-bg px-4 py-1.5 text-sm font-medium text-good">
            <Zap className="h-4 w-4" />
            How it works
          </div>
          <h2 className="mb-4 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Powered by <span className="gradient-text">advanced technology</span>
          </h2>
          <p className="text-lg text-ink-soft">
            Satellite imagery, AI analysis, and 3D visualization, combined to deliver
            an accurate solar picture of your home.
          </p>
        </motion.div>

        <div className="mb-20 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature, index) => (
            <RevealCard
              key={feature.title}
              delay={(index % 3) * 0.08}
              className="rounded-2xl border border-line bg-surface p-7 transition-colors hover:border-brand-soft/40"
            >
              <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-xl bg-good-bg text-good">
                <feature.icon className="h-6 w-6" strokeWidth={1.75} />
              </div>
              <h3 className="mb-2 text-lg font-semibold text-ink">{feature.title}</h3>
              <p className="text-sm leading-relaxed text-ink-soft">{feature.description}</p>
            </RevealCard>
          ))}
        </div>

        <motion.div
          id="benefits"
          ref={benefitsRef}
          initial={{ opacity: 0, y: 16 }}
          animate={benefitsInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.5 }}
          className="rounded-[2rem] bg-brand p-10 lg:p-12"
        >
          <div className="mb-10 text-center">
            <h3 className="mb-3 text-3xl font-bold text-white sm:text-4xl">Why choose solar?</h3>
            <p className="mx-auto max-w-2xl text-white/85">
              Join the renewable energy shift and see the benefits for yourself.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
            {benefits.map((benefit) => (
              <div
                key={benefit.subtitle}
                className="rounded-2xl border border-white/15 bg-white/10 p-6 text-center"
              >
                <benefit.icon className="mx-auto mb-3 h-8 w-8 text-white/90" strokeWidth={1.75} />
                <p className="mb-1 text-3xl font-bold text-white">{benefit.value}</p>
                <p className="text-sm font-medium text-white/80">{benefit.subtitle}</p>
              </div>
            ))}
          </div>
        </motion.div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {infoCards.map((item, index) => (
            <RevealCard
              key={item.title}
              delay={index * 0.08}
              className="flex items-start gap-4 rounded-2xl border border-line bg-surface p-6"
            >
              <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-surface-2 text-brand">
                <item.icon className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <div>
                <h4 className="mb-1 font-semibold text-ink">{item.title}</h4>
                <p className="text-sm text-ink-soft">{item.description}</p>
              </div>
            </RevealCard>
          ))}
        </div>
      </div>
    </section>
  );
}
