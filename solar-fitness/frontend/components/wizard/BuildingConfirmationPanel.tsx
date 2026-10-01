"use client";

// StartCheckWizard step "confirm-building" — the summary the customer
// sees before their rooftop polygon becomes the analysis boundary.
//
// The satellite "image preview" here is a small, non-interactive MapView
// re-render of the same live tiles the customer already saw, not a
// captured/uploaded image — consistent with this app's VIS-06 policy of
// never persisting satellite imagery (see backend providers/vision.py).

import { motion } from "framer-motion";
import { Check, Crop as CropIcon, Edit3, MapPin, PenTool, RotateCcw, Ruler } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import type { LatLngPoint } from "@/components/map/RoofBoundaryEditor";
import { Badge, Button } from "@/components/ui/Primitives";
import { approxAreaM2 } from "@/lib/geo/area";

function Stat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-paper px-3 py-2.5">
      <p className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</p>
      <p className={`mt-0.5 text-sm font-semibold text-ink ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

export function BuildingConfirmationPanel({
  address,
  method,
  centroid,
  boundary,
  onConfirm,
  onEditSelection,
  onChangeBuilding,
}: {
  address: string;
  method: "crop" | "freehand";
  centroid: { lat: number; lng: number };
  boundary: LatLngPoint[];
  onConfirm: () => void;
  onEditSelection: () => void;
  onChangeBuilding: () => void;
}) {
  const areaM2 = approxAreaM2(boundary);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="mx-auto flex h-full max-w-xl flex-col gap-4 overflow-y-auto p-4"
    >
      <div className="flex items-start gap-3">
        <span
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
          style={{ background: "var(--good-bg)", color: "var(--good)" }}
          aria-hidden="true"
        >
          <Check size={20} strokeWidth={2} />
        </span>
        <div>
          <h1 className="text-lg font-semibold text-ink">Building selected</h1>
          <p className="mt-0.5 text-sm text-ink-soft">
            This exact outline becomes the boundary for your solar analysis — every panel will stay
            inside it.
          </p>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-line shadow-sm">
        <MapView pins={[]} center={centroid} height={240} roofBoundary={boundary} />
      </div>

      <div className="flex items-center gap-2">
        <Badge tone="blue">
          {method === "crop" ? (
            <CropIcon size={11} strokeWidth={2} aria-hidden="true" />
          ) : (
            <PenTool size={11} strokeWidth={2} aria-hidden="true" />
          )}
          <span className="ml-1 capitalize">{method} selection</span>
        </Badge>
        <span className="flex items-center gap-1 text-xs text-ink-faint">
          <MapPin size={12} strokeWidth={1.75} aria-hidden="true" />
          {address || "Pinned location"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Stat label="Latitude" value={centroid.lat.toFixed(6)} mono />
        <Stat label="Longitude" value={centroid.lng.toFixed(6)} mono />
        <Stat label="Selected area" value={`${Math.round(areaM2).toLocaleString()} m²`} />
        <Stat label="Boundary points" value={String(boundary.length)} />
      </div>

      <p className="flex items-center gap-1.5 text-xs text-ink-faint">
        <Ruler size={12} strokeWidth={1.75} aria-hidden="true" />
        Area is an on-screen estimate — the backend recomputes it precisely from the same points.
      </p>

      <div className="mt-auto flex flex-col gap-2 sm:flex-row">
        <Button variant="secondary" className="flex-1" onClick={onChangeBuilding}>
          <RotateCcw size={16} strokeWidth={1.75} aria-hidden="true" /> Change building
        </Button>
        <Button variant="secondary" className="flex-1" onClick={onEditSelection}>
          <Edit3 size={16} strokeWidth={1.75} aria-hidden="true" /> Edit selection
        </Button>
        <Button className="flex-1" onClick={onConfirm}>
          <Check size={16} strokeWidth={1.75} aria-hidden="true" /> Confirm building
        </Button>
      </div>
    </motion.div>
  );
}
