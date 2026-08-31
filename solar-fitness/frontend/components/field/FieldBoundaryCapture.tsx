"use client";

import { useState } from "react";
import { Check, PenLine, RotateCcw } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import { Button } from "@/components/ui/Primitives";
import type { Site } from "@/lib/types";

export function FieldBoundaryCapture({ site }: { site: Site }) {
  const [drawing, setDrawing] = useState(false);
  const [closed, setClosed] = useState(false);

  return (
    <div className="space-y-4">
      <MapView pins={[{ id: site.id, lat: site.location.lat, lng: site.location.lng, label: site.name }]} height={360} drawEnabled />
      <div className="grid grid-cols-2 gap-3">
        <Button size="md" variant={drawing ? "primary" : "secondary"} onClick={() => setDrawing(true)} className="min-h-[56px] text-base">
          <PenLine size={18} strokeWidth={1.75} /> Draw boundary
        </Button>
        <Button size="md" variant="secondary" onClick={() => { setDrawing(false); setClosed(false); }} className="min-h-[56px] text-base">
          <RotateCcw size={18} strokeWidth={1.75} /> Reset
        </Button>
      </div>
      <Button
        size="md"
        onClick={() => setClosed(true)}
        disabled={!drawing}
        className="min-h-[60px] w-full text-base"
      >
        <Check size={20} strokeWidth={1.75} /> Close polygon &amp; submit
      </Button>
      {closed && (
        <p className="rounded-[var(--radius-app)] border p-3 text-sm" style={{ borderColor: "var(--good)", background: "var(--good-bg)", color: "var(--good)" }}>
          Boundary captured and queued for sync.
        </p>
      )}
    </div>
  );
}
