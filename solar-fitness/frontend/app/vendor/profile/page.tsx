import type { Metadata } from "next";
import { FileText, ShieldCheck, ShieldAlert, ShieldQuestion, Wallet } from "lucide-react";
import { getVendorProfileServer as getVendorProfile } from "@/lib/api/serverFetch";
import { Card, PageHeader } from "@/components/ui/Primitives";
import { formatDate } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Profile",
  description: "Verification status, documents on file, and payout method.",
};

const VERIFICATION_STYLE = {
  verified: { label: "Verified", Icon: ShieldCheck, color: "var(--good)", bg: "var(--good-bg)" },
  pending: { label: "Pending verification", Icon: ShieldQuestion, color: "var(--warn)", bg: "var(--warn-bg)" },
  rejected: { label: "Verification rejected", Icon: ShieldAlert, color: "var(--bad)", bg: "var(--bad-bg)" },
} as const;

export default async function VendorProfilePage() {
  // Falls through to a blank render rather than crashing on an
  // unauthenticated SSR pass — the layout's client-side AuthGuard redirects
  // to /login a moment after hydration in that case.
  const profile = await getVendorProfile().catch(() => null);
  if (!profile) return null;
  const verification = VERIFICATION_STYLE[profile.verificationStatus];

  return (
    <div className="space-y-6">
      <PageHeader title="Profile" description={`${profile.name} · Vendor since ${formatDate(profile.joinedAt)}`} />

      <Card className="flex items-center gap-3 p-4" style={{ borderColor: verification.color, background: verification.bg }}>
        <verification.Icon size={22} strokeWidth={1.75} style={{ color: verification.color }} aria-hidden="true" />
        <div>
          <p className="font-medium" style={{ color: verification.color }}>
            {verification.label}
          </p>
          <p className="text-sm text-ink-soft">Vendor ID {profile.vendorId}</p>
        </div>
      </Card>

      <section aria-labelledby="documents-heading">
        <h2 id="documents-heading" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Documents on file
        </h2>
        <Card className="p-4">
          <ul className="space-y-2 text-sm text-ink">
            {profile.documents.map((doc) => (
              <li key={doc} className="flex items-center gap-2">
                <FileText size={15} strokeWidth={1.75} className="text-ink-faint" aria-hidden="true" />
                {doc}
              </li>
            ))}
          </ul>
        </Card>
      </section>

      <section aria-labelledby="payout-method-heading">
        <h2 id="payout-method-heading" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          Payout method
        </h2>
        <Card className="flex items-center gap-3 p-4">
          <Wallet size={18} strokeWidth={1.75} className="text-teal" aria-hidden="true" />
          <div>
            <p className="font-medium text-ink">{profile.payoutMethod.type}</p>
            <p className="font-mono tabular text-sm text-ink-soft">{profile.payoutMethod.maskedAccount}</p>
          </div>
        </Card>
      </section>
    </div>
  );
}
