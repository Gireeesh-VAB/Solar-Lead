"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, Sun, Leaf } from "lucide-react";

export default function Navigation() {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setIsScrolled(window.scrollY > 20);
    handleScroll();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const navLinks = [
    { name: "How it works", href: "#how-it-works" },
    { name: "Solar vendors", href: "#vendors" },
    { name: "Benefits", href: "#benefits" },
    { name: "FAQ", href: "#faq" },
  ];

  return (
    <nav
      style={{ paddingTop: "env(safe-area-inset-top, 0px)" }}
      className={`fixed top-0 left-0 right-0 z-50 transition-colors duration-300 ${
        isScrolled ? "border-b border-line bg-paper/90 backdrop-blur-md" : "border-b border-transparent"
      }`}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between lg:h-18">
          <Link href="#" className="flex items-center gap-2">
            <div className="relative">
              <Sun className="h-7 w-7 text-brand" strokeWidth={1.75} />
              <Leaf className="absolute -bottom-1 -right-1 h-3.5 w-3.5 text-brand-soft" strokeWidth={1.75} />
            </div>
            <span className="text-xl font-semibold tracking-tight text-ink">
              Go<span className="text-brand">Harit</span>
            </span>
          </Link>

          <div className="hidden items-center gap-8 lg:flex">
            {navLinks.map((link) => (
              <a
                key={link.name}
                href={link.href}
                className="text-sm font-medium text-ink-soft transition-colors hover:text-ink"
              >
                {link.name}
              </a>
            ))}
          </div>

          <Link
            href="/login"
            className="hidden items-center gap-1.5 rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-soft lg:inline-flex"
          >
            Get started
          </Link>

          <button
            type="button"
            onClick={() => setIsMobileMenuOpen((v) => !v)}
            aria-label={isMobileMenuOpen ? "Close menu" : "Open menu"}
            aria-expanded={isMobileMenuOpen}
            className="rounded-lg p-2 text-ink-soft hover:text-ink lg:hidden"
          >
            {isMobileMenuOpen ? <X className="h-6 w-6" /> : <Menu className="h-6 w-6" />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-line bg-paper lg:hidden"
          >
            <div className="space-y-1 px-4 py-4">
              {navLinks.map((link) => (
                <a
                  key={link.name}
                  href={link.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className="block rounded-lg px-2 py-2.5 text-sm font-medium text-ink-soft hover:bg-surface hover:text-ink"
                >
                  {link.name}
                </a>
              ))}
              <Link
                href="/login"
                onClick={() => setIsMobileMenuOpen(false)}
                className="mt-2 block w-full rounded-full bg-brand px-6 py-3 text-center text-sm font-semibold text-white hover:bg-brand-soft"
              >
                Get started
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}
