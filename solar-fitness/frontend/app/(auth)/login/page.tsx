"use client";

import Link from "next/link";
import { useState } from "react";
import { Sun, ShieldCheck, HardHat } from "lucide-react";
import { LoginForm } from "@/components/forms/LoginForm";
import { BackButton } from "@/components/ui/BackButton";

type Portal = "customer" | "vendor" | "admin";

const PORTALS: Record<
  Portal,
  {
    label: string;
    icon: typeof Sun;
    accent: string;
    tagline: string;
    defaultEmail: string;
    defaultPassword: string;
  }
> = {
  customer: {
    label: "Customer",
    icon: Sun,
    accent: "text-amber",
    tagline: "Review site assessments and manage your portfolio.",
    defaultEmail: process.env.NEXT_PUBLIC_DEV_CUSTOMER_EMAIL ?? "",
    defaultPassword: process.env.NEXT_PUBLIC_DEV_CUSTOMER_PASSWORD ?? "",
  },
  vendor: {
    label: "Vendor",
    icon: HardHat,
    accent: "text-amber",
    tagline: "Manage installs and vendor-facing tools.",
    defaultEmail: process.env.NEXT_PUBLIC_DEV_VENDOR_EMAIL ?? "",
    defaultPassword: process.env.NEXT_PUBLIC_DEV_VENDOR_PASSWORD ?? "",
  },
  admin: {
    label: "Admin",
    icon: ShieldCheck,
    accent: "text-slate",
    tagline: "Platform administration.",
    defaultEmail: process.env.NEXT_PUBLIC_DEV_ADMIN_EMAIL ?? "",
    defaultPassword: process.env.NEXT_PUBLIC_DEV_ADMIN_PASSWORD ?? "",
  },
};

export default function LoginPage() {
  const [portal, setPortal] = useState<Portal>("customer");
  const active = PORTALS[portal];
  const Icon = active.icon;

  return (
    <main className="relative flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="absolute left-4 top-4">
        <BackButton fallbackHref="/" />
      </div>
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <Icon size={22} strokeWidth={1.75} className={active.accent} aria-hidden="true" />
          <div>
            <h1 className="text-base font-semibold text-ink">Solar Site Fitness &amp; Capacity Engine</h1>
            <p className="text-xs text-ink-soft">{active.tagline}</p>
          </div>
        </div>

        <div
          role="tablist"
          aria-label="Choose portal"
          className="mb-5 grid grid-cols-3 gap-1 rounded-[var(--radius-app)] border border-line bg-paper p-1"
        >
          {(Object.keys(PORTALS) as Portal[]).map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={portal === key}
              onClick={() => setPortal(key)}
              className={`rounded-[calc(var(--radius-app)-4px)] px-2 py-1.5 text-sm font-medium transition-colors ${
                portal === key
                  ? "bg-surface text-ink shadow-sm"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              {PORTALS[key].label}
            </button>
          ))}
        </div>

        <LoginForm
          key={portal}
          defaultEmail={active.defaultEmail}
          defaultPassword={active.defaultPassword}
        />

        {portal === "customer" && (
          <p className="mt-4 text-center text-sm text-ink-soft">
            New here?{" "}
            <Link href="/signup" className="font-medium text-blue hover:underline">
              Sign up
            </Link>
          </p>
        )}
      </div>
    </main>
  );
}
