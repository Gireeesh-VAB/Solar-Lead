"use client";

import { useEffect, useRef, useState } from "react";
import { useInView, useIsomorphicLayoutEffect, type UseInViewOptions } from "framer-motion";

// Last-resort dead-man's switch: guarantees content is never permanently
// hidden if IntersectionObserver never reports an intersection (seen in
// practice — whileInView sections have gotten stuck at their hidden state
// indefinitely). Anything this fires for is, by definition, still
// off-screen (on-screen elements are already caught by the pre-paint check
// or the observer well before this elapses), so the force-reveal is
// invisible to the user, not a jarring pop-in.
const FALLBACK_MS = 1500;

export function useScrollReveal<T extends HTMLElement = HTMLDivElement>(
  margin: NonNullable<UseInViewOptions["margin"]>
) {
  const ref = useRef<T>(null);
  const observedInView = useInView(ref, { once: true, margin, amount: 0 });
  const [preRevealed, setPreRevealed] = useState(false);
  const [timedOut, setTimedOut] = useState(false);

  // Already in/near the viewport at mount -> reveal synchronously
  // (pre-paint) instead of waiting on the async observer callback. Avoids
  // flash-of-invisible-content for above-the-fold content.
  useIsomorphicLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const buffer = 80; // roughly matches the -60px/-80px viewport margins used at call sites
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight + buffer && rect.bottom > -buffer) setPreRevealed(true);
  }, []);

  // Unconditional one-shot timer, independent of the other two signals — if
  // either already revealed the section, this later firing is a no-op (the
  // OR below stays true either way).
  useEffect(() => {
    const id = window.setTimeout(() => setTimedOut(true), FALLBACK_MS);
    return () => window.clearTimeout(id);
  }, []);

  return { ref, inView: observedInView || preRevealed || timedOut } as const;
}
