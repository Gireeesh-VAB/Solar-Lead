import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { EarningsClient } from "./EarningsClient";

export const metadata: Metadata = {
  title: "Earnings",
  description: "Payout history and pending/paid/disputed earnings breakdown.",
};

export default function VendorEarningsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Earnings" description="Your payout history, and a breakdown of pending, paid, and disputed amounts." />
      <EarningsClient />
    </div>
  );
}
