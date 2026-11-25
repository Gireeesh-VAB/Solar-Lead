"use client";

import { useState } from "react";
import { Card, Button, Badge } from "@/components/ui/Primitives";
import { useSaveElectricalAssessment } from "@/lib/query/hooks";
import type { ElectricalAssessment, VendorJob } from "@/lib/types";

const EMPTY: ElectricalAssessment = {};

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function TextField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-xs text-ink-faint">{label}</label>
      <input
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
      />
    </div>
  );
}

function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null | undefined;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink">
      <input type="checkbox" checked={value ?? false} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function PhotoField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (dataUrl: string) => void;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-soft">
      <input
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          if (file) onChange(await readAsDataUrl(file));
        }}
      />
      <span className="inline-flex items-center gap-1 rounded-[var(--radius-app)] border border-line px-2 py-1 hover:border-brand">
        {value ? "Photo attached" : `Attach ${label.toLowerCase()}`}
      </span>
      {value && <Badge tone="blue">Ready</Badge>}
    </label>
  );
}

export function ElectricalAssessmentSection({ job }: { job: VendorJob }) {
  const save = useSaveElectricalAssessment(job.id);
  const [a, setA] = useState<ElectricalAssessment>(job.electricalAssessment ?? EMPTY);
  const editable = job.status === "accepted" || job.status === "in_progress" || job.status === "sla_at_risk" || job.status === "overdue";
  const set = <K extends keyof ElectricalAssessment>(key: K, value: ElectricalAssessment[K]) => setA((prev) => ({ ...prev, [key]: value }));

  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Electrical assessment</h2>

      <fieldset disabled={!editable} className="space-y-4 disabled:opacity-60">
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Meter type" value={a.meterType} onChange={(v) => set("meterType", v)} />
          <TextField label="Meter location" value={a.meterLocation} onChange={(v) => set("meterLocation", v)} />
          <TextField label="Main DB location" value={a.mainDbLocation} onChange={(v) => set("mainDbLocation", v)} />
          <TextField label="DB condition" value={a.dbCondition} onChange={(v) => set("dbCondition", v)} />
          <TextField label="Available space" value={a.availableSpace} onChange={(v) => set("availableSpace", v)} />
          <TextField label="Cable condition" value={a.cableCondition} onChange={(v) => set("cableCondition", v)} />
          <TextField label="Earthing condition" value={a.earthingCondition} onChange={(v) => set("earthingCondition", v)} />
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <BoolField label="Smart meter" value={a.smartMeter} onChange={(v) => set("smartMeter", v)} />
          <BoolField label="Net meter" value={a.netMeter} onChange={(v) => set("netMeter", v)} />
          <BoolField label="Existing solar meter" value={a.existingSolarMeter} onChange={(v) => set("existingSolarMeter", v)} />
          <BoolField label="Earthing available" value={a.earthingAvailable} onChange={(v) => set("earthingAvailable", v)} />
          <BoolField label="Lightning protection" value={a.lightningProtectionAvailable} onChange={(v) => set("lightningProtectionAvailable", v)} />
        </div>

        <div className="flex flex-wrap gap-3">
          <PhotoField label="Meter photo" value={a.meterPhotoDataUrl} onChange={(v) => set("meterPhotoDataUrl", v)} />
          <PhotoField label="DB photo" value={a.mainDbPhotoDataUrl} onChange={(v) => set("mainDbPhotoDataUrl", v)} />
        </div>

        <div>
          <label className="mb-1 block text-xs text-ink-faint">Notes</label>
          <textarea
            value={a.notes ?? ""}
            onChange={(e) => set("notes", e.target.value)}
            rows={2}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
      </fieldset>

      {editable && (
        <Button size="sm" onClick={() => save.mutate(a)} disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Save assessment"}
        </Button>
      )}
    </Card>
  );
}
