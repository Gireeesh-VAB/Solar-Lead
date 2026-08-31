import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { ServiceAreaClient } from "./ServiceAreaClient";

export const metadata: Metadata = {
  title: "Service area",
  description: "Your coverage region and districts, and your job availability toggle.",
};

export default function VendorServiceAreaPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Service area" description="Your coverage region, and whether you're currently available for new jobs." />
      <ServiceAreaClient />
    </div>
  );
}
