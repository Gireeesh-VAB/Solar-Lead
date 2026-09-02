import type { Metadata } from "next";
import Link from "next/link";
import { HardHat } from "lucide-react";
import { LoginForm } from "@/components/forms/LoginForm";

export const metadata: Metadata = {
  title: "Vendor sign in (dev)",
  robots: { index: false, follow: false },
};

export default function VendorDevLoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm rounded-[var(--radius-app)] border border-line bg-surface p-6">
        <div className="mb-6 flex items-center gap-2">
          <HardHat size={22} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
          <div>
            <h1 className="text-base font-semibold text-ink">Vendor sign in</h1>
            <p className="text-xs text-ink-soft">Dev shortcut — credentials pre-filled</p>
          </div>
        </div>
        <LoginForm defaultEmail="vendor@test.local" defaultPassword="VendorTest123!" />
        <p className="mt-4 text-center text-sm text-ink-soft">
          Testing as an admin instead?{" "}
          <Link href="/login/admin" className="font-medium text-blue hover:underline">
            Admin sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
