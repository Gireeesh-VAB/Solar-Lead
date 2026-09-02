import type { Metadata } from "next";
import Link from "next/link";
import { Sun } from "lucide-react";
import { LoginForm } from "@/components/forms/LoginForm";

export const metadata: Metadata = {
  title: "Sign in",
  description: "Sign in to the Solar Site Fitness & Capacity Engine to review site assessments and manage your portfolio.",
  robots: { index: true, follow: true },
};

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <Sun size={22} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
          <div>
            <h1 className="text-base font-semibold text-ink">Solar Site Fitness &amp; Capacity Engine</h1>
            <p className="text-xs text-ink-soft">Sign in to your organisation workspace</p>
          </div>
        </div>
        <LoginForm />
        <p className="mt-4 text-center text-sm text-ink-soft">
          New here?{" "}
          <Link href="/signup" className="font-medium text-blue hover:underline">
            Sign up
          </Link>
        </p>
        <p className="mt-2 text-center text-xs text-ink-faint">
          Dev shortcuts:{" "}
          <Link href="/login/admin" className="underline hover:text-ink-soft">
            admin
          </Link>{" "}
          ·{" "}
          <Link href="/login/vendor" className="underline hover:text-ink-soft">
            vendor
          </Link>
        </p>
      </div>
    </main>
  );
}
