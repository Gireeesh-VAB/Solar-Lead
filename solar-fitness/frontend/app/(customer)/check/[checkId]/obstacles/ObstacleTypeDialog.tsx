"use client";

// "What type of obstacle is this?" - the pop-up that opens when the customer
// confirms a detection (or saves an obstacle they drew). One tap on a type
// answers it AND closes the pop-up; the next obstacle's Confirm opens it again.
//
// The list, the labels and the heights are the VAB Design Studio's own
// (ObstacleAreaDialog / STANDARD_OBSTACLE_DIMS), so both products ask the
// same question the same way. The icons are TYPE_META's, the one place the
// result page and this screen take them from.

import { useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";
import type { ObstacleType } from "@/lib/api/client";
import { TYPE_META } from "../result/ObstructionsList";

/** What the picker offers, in the order it reads. `heightM` is the type's standard rooftop height. */
export const OBSTACLE_CHOICES: { value: ObstacleType; label: string; heightM: number }[] = [
  { value: "water_tank", label: "Water Tank", heightM: 2 },
  { value: "staircase", label: "Staircase / Mumty", heightM: 2.7 },
  { value: "hvac_unit", label: "HVAC / AC Outdoor Unit", heightM: 1 },
  { value: "lift_room", label: "Lift Room", heightM: 2.7 },
  { value: "chimney", label: "Chimney / Vent", heightM: 3 },
  { value: "solar_water_heater", label: "Solar Water Heater", heightM: 1.6 },
  { value: "parapet", label: "Parapet Structure", heightM: 1 },
  { value: "electrical_equipment", label: "Electrical Equipment", heightM: 1.8 },
  { value: "existing_solar_panel", label: "Existing Solar Panels", heightM: 1 },
  { value: "tree", label: "Tree", heightM: 4 },
  { value: "walkway", label: "Walkway / Maintenance Access", heightM: 0.15 },
  { value: "other", label: "Other", heightM: 1.5 },
];

export function ObstacleTypeDialog({
  open,
  saving = false,
  onPick,
  onCancel,
}: {
  open: boolean;
  /** An answer is being saved: the list is locked until it finishes. */
  saving?: boolean;
  /** The customer chose a type. The caller saves it and closes the pop-up. */
  onPick: (type: ObstacleType) => void;
  onCancel: () => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("[data-type-tile]")?.focus();
    // The page behind must not scroll while the pop-up is open.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && !saving) onCancel();
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>("button:not([disabled])");
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, saving, onCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !saving) onCancel();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="obstacle-type-title"
        className="flex max-h-[88dvh] w-full max-w-md flex-col rounded-[var(--radius-app)] border border-line bg-paper shadow-[var(--shadow-float)]"
      >
        <h2 id="obstacle-type-title" className="px-6 pb-2 pt-5 text-lg font-semibold text-ink">
          What type of obstacle is this?
        </h2>

        <div
          className="grid min-h-0 grid-cols-3 gap-2 overflow-y-auto px-6 py-3"
          style={{ opacity: saving ? 0.5 : 1, pointerEvents: saving ? "none" : "auto" }}
        >
          {OBSTACLE_CHOICES.map(({ value, label, heightM }) => {
            const Icon = TYPE_META[value].icon;
            return (
              <button
                key={value}
                type="button"
                data-type-tile
                onClick={() => onPick(value)}
                className="flex flex-col items-center gap-1 self-start rounded-[var(--radius-app)] border border-line bg-paper px-1.5 py-3 text-center transition-colors hover:border-blue hover:bg-surface-2 focus-visible:border-blue focus-visible:outline-none"
              >
                <Icon size={18} strokeWidth={1.75} className="text-ink" aria-hidden="true" />
                <span className="text-xs font-medium leading-tight text-ink">{label}</span>
                <span className="text-[10px] leading-tight text-ink-faint">{heightM} m high</span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-end gap-3 px-6 pb-4 pt-2">
          {saving && (
            <span className="inline-flex items-center gap-1.5 text-sm text-ink-soft" role="status">
              <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Adding…
            </span>
          )}
          <button
            type="button"
            onClick={onCancel}
            disabled={saving}
            className="rounded-[var(--radius-app)] px-2 py-1.5 text-sm font-semibold text-blue transition-opacity hover:opacity-80 disabled:opacity-60"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
