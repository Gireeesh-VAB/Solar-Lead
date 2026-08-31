import type { Metadata } from "next";
import Link from "next/link";
import { Sun } from "lucide-react";
import { SignupForm } from "@/components/forms/SignupForm";

export const metadata: Metadata = {
  title: "Sign up",
  description: "Create your account to check whether solar works at your location.",
  robots: { index: true, follow: true },
};

export default function SignupPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <Sun size={22} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
          <div>
            <h1 className="text-base font-semibold text-ink">Solar Site Fitness &amp; Capacity Engine</h1>
            <p className="text-xs text-ink-soft">Create your account</p>
          </div>
        </div>
        <SignupForm />
        <p className="mt-4 text-center text-sm text-ink-soft">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-blue hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
