import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { PerformanceClient } from "./PerformanceClient";

export const metadata: Metadata = {
  title: "Performance",
  description: "Accuracy score trend and jobs broken down by measurement variance band.",
};

export default function VendorPerformancePage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Performance" description="Your accuracy score trend, and how your submissions compare to measured values." />
      <PerformanceClient />
    </div>
  );
}
