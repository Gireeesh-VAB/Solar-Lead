import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AdminModelsClient } from "./AdminModelsClient";

export const metadata: Metadata = {
  title: "Model approval",
  description: "Review candidate ML model versions against the active model and approve or hold promotion.",
};

export default function AdminModelsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Model approval" description="Compare candidate model versions against the active production model." />
      <AdminModelsClient />
    </div>
  );
}
