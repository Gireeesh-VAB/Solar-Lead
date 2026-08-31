import type { Metadata } from "next";
import Link from "next/link";
import { Building2, MapPinned, UploadCloud } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";

export const metadata: Metadata = {
  title: "Onboarding",
  description: "Set up your organisation, jurisdictions, and first site portfolio import.",
  robots: { index: true, follow: true },
};

const STEPS = [
  {
    icon: Building2,
    title: "Organisation profile",
    description: "Confirm your organisation name, primary jurisdictions, and default site types you assess.",
  },
  {
    icon: UploadCloud,
    title: "Import your first sites",
    description: "Upload a CSV/XLSX of candidate sites, or add them one at a time from an address or map pin.",
  },
  {
    icon: MapPinned,
    title: "Run your first assessment",
    description: "The engine returns a verdict, capacity, confidence tier, and binding constraint for each site.",
  },
];

export default function OnboardingPage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-4 py-12">
      <h1 className="text-2xl font-semibold text-ink">Welcome — let&apos;s set up your workspace</h1>
      <p className="mt-2 text-sm text-ink-soft">
        Three steps to get your first site fitness assessment. You can revisit each step later from Settings.
      </p>
      <ol className="mt-8 space-y-3">
        {STEPS.map((step, i) => (
          <li key={step.title}>
            <Card className="flex items-start gap-3 p-4">
              <span
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[var(--radius-app)] font-mono text-sm font-semibold"
                style={{ background: "var(--surface-2)", color: "var(--blue)" }}
                aria-hidden="true"
              >
                {i + 1}
              </span>
              <div>
                <div className="flex items-center gap-2">
                  <step.icon size={16} strokeWidth={1.75} className="text-blue" aria-hidden="true" />
                  <p className="font-medium text-ink">{step.title}</p>
                </div>
                <p className="mt-1 text-sm text-ink-soft">{step.description}</p>
              </div>
            </Card>
          </li>
        ))}
      </ol>
      <div className="mt-8 flex justify-end gap-2">
        <Link href="/home">
          <Button variant="secondary">Skip for now</Button>
        </Link>
        <Link href="/check/new">
          <Button>Check your first location</Button>
        </Link>
      </div>
    </main>
  );
}
