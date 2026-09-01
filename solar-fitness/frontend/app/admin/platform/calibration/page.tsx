import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminCalibrationClient } from "./AdminCalibrationClient";

export const metadata: Metadata = {
  title: "Calibration approvals",
  description: "Review calibration proposals derived from field-measured variance and approve or reject.",
};

export default function AdminCalibrationPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Calibration" description="Recalibration proposals derived from remote-vs-field variance, pending approval." />
      <AdminCalibrationClient />
    </div>
  );
}
