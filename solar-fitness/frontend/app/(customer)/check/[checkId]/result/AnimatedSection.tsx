"use client";

// Scroll-triggered fade/rise-in for the result page's sections — same
// fadeUp motion language as HomeClient.tsx, but scroll-triggered rather
// than animate-on-mount since this page is long enough that most sections
// start off-screen. Uses useScrollReveal (lib/hooks) rather than framer's
// raw whileInView prop directly — whileInView's IntersectionObserver has
// been observed to never fire for some sections, leaving them permanently
// invisible; the hook adds fallbacks so visibility never depends on the
// observer alone. Purely presentational: wraps server-rendered children,
// never touches what they render.

import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useScrollReveal } from "@/lib/hooks/useScrollReveal";

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0 },
};

export function AnimatedSection({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  const { ref, inView } = useScrollReveal("-60px 0px");
  return (
    <motion.div
      ref={ref}
      initial="hidden"
      animate={inView ? "show" : "hidden"}
      variants={fadeUp}
      transition={{ duration: 0.45, ease: "easeOut" }}
      className={className}
    >
      {children}
    </motion.div>
  );
}
