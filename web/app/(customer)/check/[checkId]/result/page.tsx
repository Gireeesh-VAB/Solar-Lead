import type { Metadata } from "next";
import { ResultClient } from "./ResultClient";

export const metadata: Metadata = {
  title: "Your result",
  robots: { index: false, follow: false },
};

export default async function ResultPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  return <ResultClient checkId={checkId} />;
}
