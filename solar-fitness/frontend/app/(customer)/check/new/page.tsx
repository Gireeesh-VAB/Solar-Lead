import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { NewCheckForm } from "./NewCheckForm";

export const metadata: Metadata = {
  title: "Check a new location",
  robots: { index: false, follow: false },
};

export default function NewCheckPage() {
  return (
    <div className="mx-auto max-w-xl space-y-6">
      <PageHeader
        title="Check a new location"
        description="Search for an address, use your current location, or drop a pin on the map."
      />
      <NewCheckForm />
    </div>
  );
}
