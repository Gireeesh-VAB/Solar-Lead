import type { Metadata } from "next";
import { ProcessingClient } from "./ProcessingClient";

export const metadata: Metadata = {
  title: "Checking your location",
  robots: { index: false, follow: false },
};

export default async function ProcessingPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  return <ProcessingClient checkId={checkId} />;
}
