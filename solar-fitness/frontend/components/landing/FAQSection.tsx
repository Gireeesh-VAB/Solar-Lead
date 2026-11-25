"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, HelpCircle } from "lucide-react";
import { useScrollReveal } from "@/lib/hooks/useScrollReveal";

const faqs = [
  {
    question: "How accurate is the satellite analysis?",
    answer:
      "Our satellite imagery analysis is highly accurate, typically within 5% of actual measurements. We use high-resolution imagery combined with AI to calculate roof dimensions, angles, and potential shading from nearby structures or trees.",
  },
  {
    question: "Is the initial analysis really free?",
    answer:
      "Yes. Your initial solar feasibility analysis is completely free with no strings attached. You'll get a detailed report including roof measurements, solar potential, estimated energy production, and projected savings. There's no obligation to proceed with installation.",
  },
  {
    question: "How long does the installation process take?",
    answer:
      "The timeline varies based on your location and system size, but residential installations typically take 1-3 days once permits are approved. The entire process, from signing a contract to turning on your system, usually takes 4-8 weeks.",
  },
  {
    question: "What happens on cloudy days or at night?",
    answer:
      "Solar panels still generate electricity on cloudy days, though at reduced capacity. For nighttime and low-production periods, you can draw from the grid (net metering) or install a battery storage system to use stored solar energy.",
  },
  {
    question: "How do I choose the right solar vendor?",
    answer:
      "We show you verified, top-rated installers in your area with transparent reviews and credentials. Consider experience, warranty terms, pricing, and customer reviews — our platform makes it easy to compare and get quotes from multiple vendors.",
  },
  {
    question: "Are there financing options available?",
    answer:
      "Yes. Most solar vendors offer financing options including solar loans, leases, and power purchase agreements. Many homeowners also qualify for federal tax credits and local rebates that significantly reduce costs.",
  },
];

export default function FAQSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);
  const { ref, inView } = useScrollReveal("-80px");

  return (
    <section id="faq" className="bg-paper py-20 lg:py-24">
      <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 16 }}
          animate={inView ? { opacity: 1, y: 0 } : { opacity: 0, y: 16 }}
          transition={{ duration: 0.5 }}
          className="mb-14 text-center"
        >
          <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-good-bg px-4 py-1.5 text-sm font-medium text-good">
            <HelpCircle className="h-4 w-4" />
            Got questions?
          </div>
          <h2 className="mb-4 text-4xl font-bold tracking-tight text-ink sm:text-5xl">
            Frequently asked <span className="gradient-text">questions</span>
          </h2>
          <p className="text-lg text-ink-soft">Everything you need to know about going solar with GoHarit</p>
        </motion.div>

        <div className="space-y-3">
          {faqs.map((faq, index) => {
            const isOpen = openIndex === index;
            return (
              <div
                key={faq.question}
                className={`overflow-hidden rounded-2xl border bg-surface transition-colors ${
                  isOpen ? "border-brand-soft/50" : "border-line"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setOpenIndex(isOpen ? null : index)}
                  aria-expanded={isOpen}
                  className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
                >
                  <span className="font-semibold text-ink">{faq.question}</span>
                  <motion.span
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ duration: 0.2 }}
                    className={`flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full ${
                      isOpen ? "bg-brand text-white" : "bg-surface-2 text-ink-soft"
                    }`}
                  >
                    <ChevronDown className="h-5 w-5" />
                  </motion.span>
                </button>

                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.2 }}
                    >
                      <p className="border-t border-line px-6 pb-5 pt-4 leading-relaxed text-ink-soft">
                        {faq.answer}
                      </p>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>

        <div className="mt-12 text-center">
          <p className="mb-4 text-ink-soft">Still have questions? We&apos;re here to help.</p>
          <a
            href="mailto:hello@goharit.com"
            className="inline-flex items-center gap-2 rounded-full bg-brand px-8 py-3.5 font-semibold text-white transition-colors hover:bg-brand-soft"
          >
            Contact support
          </a>
        </div>
      </div>
    </section>
  );
}
