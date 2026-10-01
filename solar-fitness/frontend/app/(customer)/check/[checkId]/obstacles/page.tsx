import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getCheckServer as getCheck } from "@/lib/api/serverFetch";
import { ObstacleMarkerClient } from "./ObstacleMarkerClient";

export const metadata: Metadata = {
  title: "What's on your roof",
  robots: { index: false, follow: false },
};

export default async function ObstaclesPage({ params }: { params: Promise<{ checkId: string }> }) {
  const { checkId } = await params;
  const check = await getCheck(checkId).catch(() => null);
  if (!check) notFound();

  return (
    <div className="mx-auto max-w-xl">
      <ObstacleMarkerClient check={check} />
    </div>
  );
}
