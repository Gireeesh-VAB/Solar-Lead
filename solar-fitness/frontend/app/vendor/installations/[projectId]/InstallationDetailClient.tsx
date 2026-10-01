"use client";

// The crew's on-site screen. Four panels over the one project: stage
// advance, the QC checklist, geotagged photo capture, and the
// commissioning handover — mirroring vendor/jobs/[jobId]'s
// "read-only summary + a stack of independently-saved sections" shape,
// but colocated in one file (like admin's AssessmentReviewClient) since
// each section here is a dozen lines rather than a full survey form.

import { useState } from "react";
import { motion } from "framer-motion";
import { Camera, CheckCircle2, ClipboardCheck, MapPin, Zap } from "lucide-react";
import {
  useAddInstallationPhoto,
  useAdvanceInstallationStatus,
  useInstallationPhotos,
  useSubmitCommissioning,
  useSubmitInstallationQc,
  useSaveInstallationQc,
  useVendorCommissioning,
  useVendorInstallation,
  useVendorInstallationQc,
} from "@/lib/query/hooks";
import { Badge, Button, Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { Select } from "@/components/ui/Select";
import { StageProgress, stageLabel } from "@/components/installations/StageProgress";
import {
  QC_CHECKLIST_ITEMS,
  QC_CHECKLIST_LABEL,
  type CommissioningRecord,
  type InstallationProject,
  type InstallationQcItems,
} from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

const fadeUp = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0 } };
const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.07, delayChildren: 0.04 } } };

export function InstallationDetailClient({ projectId }: { projectId: string }) {
  const project = useVendorInstallation(projectId);

  if (project.isLoading) {
    return (
      <div className="space-y-4">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  if (project.isError || !project.data) {
    return (
      <ErrorState
        description="Could not load this installation project."
        onRetry={() => project.refetch()}
      />
    );
  }

  const p = project.data;
  return (
    <motion.div
      variants={stagger}
      initial="hidden"
      animate="show"
      className="grid grid-cols-1 gap-4 lg:grid-cols-3"
    >
      <div className="space-y-4 lg:col-span-2">
        <motion.div variants={fadeUp}>
          <SummaryCard project={p} />
        </motion.div>
        <motion.div variants={fadeUp}>
          <QcSection projectId={projectId} />
        </motion.div>
        <motion.div variants={fadeUp}>
          <PhotoSection projectId={projectId} currentStage={p.status} />
        </motion.div>
        <motion.div variants={fadeUp}>
          <CommissioningSection projectId={projectId} />
        </motion.div>
      </div>
      <motion.div variants={fadeUp} className="space-y-4">
        <StageCard project={p} />
      </motion.div>
    </motion.div>
  );
}

function SummaryCard({ project }: { project: InstallationProject }) {
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[var(--good-bg)] text-brand"
            aria-hidden="true"
          >
            <Zap size={20} strokeWidth={1.75} />
          </span>
          <div>
            <h1 className="text-lg font-semibold text-ink">
              {project.approvedCapacityKwp.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWp
              installation
            </h1>
            <p className="mt-0.5 text-xs text-ink-soft">
              Opened {formatDateTime(project.createdAt)} · updated{" "}
              {formatDateTime(project.updatedAt)}
            </p>
          </div>
        </div>
        <Badge tone={project.status === "completed" ? "blue" : "neutral"}>
          {stageLabel(project.status)}
        </Badge>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-3">
        <Stat label="Approved capacity" value={`${project.approvedCapacityKwp} kWp`} />
        <Stat label="Panel model" value={project.panelModel ?? "Not recorded"} />
        <Stat label="Inverter model" value={project.inverterModel ?? "Not recorded"} />
      </dl>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-app)] bg-surface-2 px-3 py-2.5">
      <dt className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-0.5 truncate text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}

function StageCard({ project }: { project: InstallationProject }) {
  const advance = useAdvanceInstallationStatus(project.id);
  const [panelModel, setPanelModel] = useState(project.panelModel ?? "");
  const [inverterModel, setInverterModel] = useState(project.inverterModel ?? "");

  // "completed" is admin-only (only commissioning approval ends a
  // project), so it never appears as a target here.
  const selectable = project.stages.filter((s) => s !== "completed");
  const locked = project.status === "completed";

  return (
    <Card className="space-y-4 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Stage</h2>
      <StageProgress
        stages={project.stages}
        stageIndex={project.stageIndex}
        className="max-h-[22rem] overflow-y-auto scrollbar-thin pr-1"
      />
      <fieldset disabled={locked} className="space-y-2 border-t border-line pt-4 disabled:opacity-60">
        <label className="block text-xs text-ink-soft" htmlFor="panel-model">
          Panel model
        </label>
        <input
          id="panel-model"
          value={panelModel}
          onChange={(e) => setPanelModel(e.target.value)}
          placeholder="e.g. Adani 540W mono PERC"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
        />
        <label className="block text-xs text-ink-soft" htmlFor="inverter-model">
          Inverter model
        </label>
        <input
          id="inverter-model"
          value={inverterModel}
          onChange={(e) => setInverterModel(e.target.value)}
          placeholder="e.g. Growatt MIN 5000TL-X"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
        />
        <label className="block pt-2 text-xs text-ink-soft" htmlFor="next-stage">
          Move to stage
        </label>
        <Select
          id="next-stage"
          value={project.status === "completed" ? "" : project.status}
          onChange={(e) =>
            advance.mutate({
              status: e.target.value,
              panelModel: panelModel || undefined,
              inverterModel: inverterModel || undefined,
            })
          }
          className="w-full"
        >
          {selectable.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
      </fieldset>
      {advance.isPending && <p className="text-xs text-ink-faint">Saving…</p>}
      {locked && (
        <p className="text-xs text-ink-faint">
          This project is completed — the admin&apos;s commissioning approval closed it.
        </p>
      )}
    </Card>
  );
}

function QcSection({ projectId }: { projectId: string }) {
  const qc = useVendorInstallationQc(projectId);
  const save = useSaveInstallationQc(projectId);
  const submit = useSubmitInstallationQc(projectId);
  // Derived, not synced: the draft is null until the crew touches
  // something, so the server value shows through until then and a
  // background refetch can never wipe half-entered work.
  const [draft, setDraft] = useState<InstallationQcItems | null>(null);
  const [notesDraft, setNotesDraft] = useState<string | null>(null);
  const items = draft ?? qc.data?.checklist ?? {};
  const notes = notesDraft ?? qc.data?.notes ?? "";

  const approved = qc.data?.approvedAt != null;
  const submitted = qc.data?.submittedAt != null;
  const set = (key: string, value: boolean | null) =>
    setDraft((prev) => ({ ...(prev ?? qc.data?.checklist ?? {}), [key]: value }));
  const setNotes = (value: string) => setNotesDraft(value);
  const payload = { checklist: items, notes: notes || null };

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
          <ClipboardCheck size={15} strokeWidth={1.75} aria-hidden="true" />
          Quality checklist
        </h2>
        <Badge tone={approved ? "blue" : submitted ? "amber" : "neutral"}>
          {approved ? "Approved" : submitted ? "Submitted" : "Draft"}
        </Badge>
      </div>

      {qc.isLoading && <p className="text-sm text-ink-faint">Loading checklist…</p>}

      <fieldset disabled={approved} className="space-y-1.5 disabled:opacity-60">
        {QC_CHECKLIST_ITEMS.map((key) => (
          <div
            key={key}
            className="flex items-center justify-between gap-3 rounded-[var(--radius-app)] px-2 py-1.5 hover:bg-surface-2"
          >
            <span className="text-sm text-ink">{QC_CHECKLIST_LABEL[key] ?? key}</span>
            <div className="flex shrink-0 gap-1">
              {/* Three-state on purpose: null ("not inspected") is a real
                  answer the backend stores, distinct from a failed check. */}
              {(
                [
                  { value: true, label: "Pass" },
                  { value: false, label: "Fail" },
                  { value: null, label: "N/A" },
                ] as const
              ).map((opt) => (
                <button
                  key={opt.label}
                  type="button"
                  onClick={() => set(key, opt.value)}
                  aria-pressed={items[key] === opt.value}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 text-[11px] transition-colors",
                    items[key] === opt.value
                      ? opt.value === true
                        ? "border-brand bg-brand text-white"
                        : opt.value === false
                          ? "border-[var(--bad)] bg-[var(--bad)] text-white"
                          : "border-ink-faint bg-ink-faint text-white"
                      : "border-line bg-paper text-ink-soft hover:border-ink-faint"
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        <label className="block pt-3 text-xs text-ink-soft" htmlFor="qc-notes">
          Notes
        </label>
        <textarea
          id="qc-notes"
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Anything the reviewer should know about the items above."
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
        />
      </fieldset>

      {!approved && (
        <div className="flex flex-wrap gap-2 border-t border-line pt-3">
          <Button
            size="sm"
            variant="secondary"
            disabled={save.isPending}
            onClick={() => save.mutate(payload)}
          >
            {save.isPending ? "Saving…" : "Save draft"}
          </Button>
          <Button size="sm" disabled={submit.isPending} onClick={() => submit.mutate(payload)}>
            <CheckCircle2 size={14} strokeWidth={1.75} />
            {submit.isPending ? "Submitting…" : submitted ? "Resubmit for review" : "Submit for review"}
          </Button>
        </div>
      )}
      {approved && qc.data?.approvedAt && (
        <p className="border-t border-line pt-3 text-xs text-ink-faint">
          Approved {formatDateTime(qc.data.approvedAt)} — this checklist is now locked.
        </p>
      )}
    </Card>
  );
}

function PhotoSection({ projectId, currentStage }: { projectId: string; currentStage: string }) {
  const photos = useInstallationPhotos(projectId);
  const add = useAddInstallationPhoto(projectId);
  const [stage, setStage] = useState(currentStage);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);

  // The location is read once, on demand, rather than watched — a
  // progress photo needs where it was taken, not a live track.
  const readLocation = () => {
    if (!navigator.geolocation) {
      setGeoError("This device has no location support.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setGeoError(null);
      },
      () => setGeoError("Location unavailable — the photo will be saved without coordinates.")
    );
  };

  const onFile = (file: File | undefined) => {
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () =>
      add.mutate({
        stage,
        dataUrl: String(reader.result),
        lat: coords?.lat ?? null,
        lng: coords?.lng ?? null,
      });
    reader.readAsDataURL(file);
  };

  return (
    <Card className="space-y-4 p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
        <Camera size={15} strokeWidth={1.75} aria-hidden="true" />
        Progress photos
      </h2>

      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={stage}
          onChange={(e) => setStage(e.target.value)}
          aria-label="Photo stage"
        >
          {PHOTO_STAGE_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </Select>
        <Button size="sm" variant="secondary" onClick={readLocation} type="button">
          <MapPin size={14} strokeWidth={1.75} />
          {coords ? `${coords.lat.toFixed(5)}, ${coords.lng.toFixed(5)}` : "Tag location"}
        </Button>
        <label className="cursor-pointer rounded-[var(--radius-app)] border border-line bg-paper px-3 py-1.5 text-sm text-ink hover:border-brand">
          {add.isPending ? "Uploading…" : "Add photo"}
          <input
            type="file"
            accept="image/*"
            capture="environment"
            className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])}
          />
        </label>
      </div>
      {geoError && <p className="text-xs text-ink-faint">{geoError}</p>}

      {photos.data && photos.data.length > 0 ? (
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {photos.data.map((photo) => (
            <li key={photo.id} className="overflow-hidden rounded-[var(--radius-app)] border border-line">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={photo.dataUrl} alt={`${stageLabel(photo.stage)} progress`} className="h-28 w-full object-cover" />
              <div className="px-2 py-1.5">
                <p className="truncate text-[11px] font-medium text-ink">{stageLabel(photo.stage)}</p>
                <p className="truncate text-[11px] text-ink-faint">
                  {photo.lat != null && photo.lng != null
                    ? `${photo.lat.toFixed(4)}, ${photo.lng.toFixed(4)}`
                    : "No location"}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-faint">No photos captured yet.</p>
      )}
    </Card>
  );
}

// The stages a photo is actually taken at — "created" (an admin
// bookkeeping state) and "completed" (nothing left to photograph) are
// omitted, so the picker isn't padded with unusable options.
const PHOTO_STAGE_OPTIONS = [
  "material_delivered",
  "installation_started",
  "mounting_installed",
  "panels_installed",
  "inverter_installed",
  "dc_wiring",
  "ac_wiring",
  "earthing",
  "lightning_protection",
  "electrical_testing",
  "inspection",
  "net_metering",
  "commissioning",
];

function CommissioningSection({ projectId }: { projectId: string }) {
  const record = useVendorCommissioning(projectId);
  const submit = useSubmitCommissioning(projectId);
  // Same derive-don't-sync approach as the checklist above.
  const [draft, setDraft] = useState<Partial<CommissioningRecord> | null>(null);
  const form = draft ?? record.data ?? {};

  const locked = record.data?.adminApproved === true;
  const set = <K extends keyof CommissioningRecord>(key: K, value: CommissioningRecord[K]) =>
    setDraft((prev) => ({ ...(prev ?? record.data ?? {}), [key]: value }));

  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Commissioning</h2>
        <Badge tone={locked ? "blue" : record.data?.vendorConfirmed ? "amber" : "neutral"}>
          {locked ? "Approved" : record.data?.vendorConfirmed ? "Awaiting approval" : "Not submitted"}
        </Badge>
      </div>

      <fieldset disabled={locked} className="grid grid-cols-1 gap-3 sm:grid-cols-2 disabled:opacity-60">
        <NumberField
          label="Installed capacity (kWp)"
          value={form.installedCapacityKwp ?? null}
          onChange={(v) => set("installedCapacityKwp", v)}
        />
        <NumberField
          label="Panel count"
          value={form.installedPanelCount ?? null}
          onChange={(v) => set("installedPanelCount", v)}
        />
        <TextField
          label="Inverter serial number"
          value={form.inverterSerialNumber ?? ""}
          onChange={(v) => set("inverterSerialNumber", v)}
        />
        <TextField
          label="Meter number"
          value={form.meterNumber ?? ""}
          onChange={(v) => set("meterNumber", v)}
        />
        <NumberField
          label="Voltage reading (V)"
          value={form.voltageReading ?? null}
          onChange={(v) => set("voltageReading", v)}
        />
        <NumberField
          label="Current reading (A)"
          value={form.currentReading ?? null}
          onChange={(v) => set("currentReading", v)}
        />
        <TextField
          label="Panel serial numbers (comma separated)"
          value={(form.panelSerialNumbers ?? []).join(", ")}
          onChange={(v) =>
            set(
              "panelSerialNumbers",
              v
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          className="sm:col-span-2"
        />
        <BoolField
          label="Earthing test passed"
          value={form.earthingTestPassed ?? null}
          onChange={(v) => set("earthingTestPassed", v)}
        />
        <BoolField
          label="Insulation test passed"
          value={form.insulationTestPassed ?? null}
          onChange={(v) => set("insulationTestPassed", v)}
        />
      </fieldset>

      {!locked && (
        <div className="border-t border-line pt-3">
          <Button
            size="sm"
            disabled={submit.isPending}
            onClick={() =>
              submit.mutate({
                installedCapacityKwp: form.installedCapacityKwp ?? null,
                installedPanelCount: form.installedPanelCount ?? null,
                panelSerialNumbers: form.panelSerialNumbers ?? [],
                inverterSerialNumber: form.inverterSerialNumber ?? null,
                meterNumber: form.meterNumber ?? null,
                voltageReading: form.voltageReading ?? null,
                currentReading: form.currentReading ?? null,
                earthingTestPassed: form.earthingTestPassed ?? null,
                insulationTestPassed: form.insulationTestPassed ?? null,
              })
            }
          >
            {submit.isPending ? "Submitting…" : "Submit commissioning"}
          </Button>
          <p className="mt-2 text-xs text-ink-faint">
            Submitting confirms the install on your side. The customer signs off next, then an admin
            approves — which is what marks the project completed.
          </p>
        </div>
      )}
    </Card>
  );
}

function TextField({
  label,
  value,
  onChange,
  className,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      <span className="block text-xs text-ink-soft">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-ink-soft">{label}</span>
      <input
        type="number"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="mt-1 w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-brand focus:ring-2 focus:ring-brand/25"
      />
    </label>
  );
}

function BoolField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (value: boolean | null) => void;
}) {
  return (
    <label className="block">
      <span className="block text-xs text-ink-soft">{label}</span>
      <Select
        value={value === null || value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value === "true")}
        className="mt-1 w-full"
      >
        <option value="">Not tested</option>
        <option value="true">Passed</option>
        <option value="false">Failed</option>
      </Select>
    </label>
  );
}
