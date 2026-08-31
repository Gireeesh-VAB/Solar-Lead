"use client";

import { useState } from "react";
import { MapPinned, ScanLine } from "lucide-react";
import { FieldBoundaryCapture } from "@/components/field/FieldBoundaryCapture";
import { UsnCaptureFlow } from "@/components/sites/UsnCaptureFlow";
import { cn } from "@/lib/utils";
import type { Site } from "@/lib/types";

type Tab = "boundary" | "usn";

export function CaptureTabs({ site, showUsn }: { site: Site; showUsn: boolean }) {
  const [tab, setTab] = useState<Tab>("boundary");

  return (
    <div className="space-y-4">
      {showUsn && (
        <div className="flex gap-2 border-b border-line">
          <TabButton active={tab === "boundary"} onClick={() => setTab("boundary")} icon={MapPinned} label="Boundary" />
          <TabButton active={tab === "usn"} onClick={() => setTab("usn")} icon={ScanLine} label="USN" />
        </div>
      )}
      {tab === "boundary" && <FieldBoundaryCapture site={site} />}
      {tab === "usn" && showUsn && <UsnCaptureFlow site={site} mobile />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon: Icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: typeof MapPinned;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm font-medium",
        active ? "border-teal text-ink" : "border-transparent text-ink-soft hover:text-ink"
      )}
    >
      <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
      {label}
    </button>
  );
}
