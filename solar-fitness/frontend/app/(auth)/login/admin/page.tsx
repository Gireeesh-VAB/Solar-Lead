import type { Metadata } from "next";
import Link from "next/link";
import { ShieldCheck } from "lucide-react";
import { LoginForm } from "@/components/forms/LoginForm";
import { BackButton } from "@/components/ui/BackButton";

export const metadata: Metadata = {
  title: "Admin sign in (dev)",
  robots: { index: false, follow: false },
};

export default function AdminDevLoginPage() {
  return (
    <main className="relative flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="absolute left-4 top-4">
        <BackButton fallbackHref="/login" />
      </div>
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <ShieldCheck size={22} strokeWidth={1.75} className="text-slate" aria-hidden="true" />
          <div>
            <h1 className="text-base font-semibold text-ink">Admin sign in</h1>
            <p className="text-xs text-ink-soft">Dev shortcut — credentials pre-filled</p>
          </div>
        </div>
        <LoginForm
          defaultEmail={process.env.NEXT_PUBLIC_DEV_ADMIN_EMAIL ?? ""}
          defaultPassword={process.env.NEXT_PUBLIC_DEV_ADMIN_PASSWORD ?? ""}
        />
        <p className="mt-4 text-center text-sm text-ink-soft">
          Testing as a vendor instead?{" "}
          <Link href="/login/vendor" className="font-medium text-blue hover:underline">
            Vendor sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
