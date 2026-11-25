"use client";

// "What's on your roof?" — the step right after the customer has selected
// their roof, BEFORE the assessment.
//
// On arrival the roof is scanned for obstacles (water tanks, stair rooms,
// equipment…) by the detector models. What they find is NOT applied: each
// detection is shown as a numbered, dashed area on the map and as a row in
// a review list — "#1 Detected obstacle · 84% confidence" — with
//
//   Confirm  apply it: the panels are then laid out clear of it
//   Edit     correct its type and/or drag its outline to fit, then confirm
//   Ignore   it isn't real: dismissed, and not offered again
//
// Until the customer confirms a detection it counts toward neither panel
// placement nor shading. The customer is the check on the models. They can
// also tap the map to add anything that was missed, and remove anything
// they've confirmed.
//
// Nothing here is a parallel obstacle system: a confirmed detection and a
// hand-placed marker go through the same OBS-03 validation and are unioned
// into the same site.exclusions with the same provenance record.

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CircleHelp,
  Loader2,
  RefreshCw,
  ScanSearch,
  Sparkles,
  Trash2,
} from "lucide-react";
import { MapView } from "@/components/map/MapView";
import { RoofBoundaryEditor } from "@/components/map/RoofBoundaryEditor";
import { Button } from "@/components/ui/Primitives";
import type { ObstacleType } from "@/lib/api/client";
import {
  useCheckObstacles,
  useConfirmCheckObstacle,
  useDetectCheckObstacles,
  useIgnoreCheckObstacle,
  useMarkCheckObstacle,
  useUnmarkCheckObstacle,
} from "@/lib/query/hooks";
import type { Site } from "@/lib/types";
import { TYPE_META } from "../result/ObstructionsList";

// The order the palette reads in — commonest rooftop objects first, and
// "Other structure" last as the catch-all. The icons and labels are
// TYPE_META's own, not a second set: a marked water tank has to look
// exactly like a detected one on the result page.
const PALETTE: ObstacleType[] = [
  "water_tank",
  "hvac_unit",
  "chimney",
  "existing_solar_panel",
  "vent",
  "antenna",
  "other",
];

// The server's own source values (routers/app_checks.py): a customer's
// placement, and a detection by the detector models. The customer may
// remove both once they're on the roof.
const CUSTOMER_MARKED = "customer_marked";
const MODEL_DETECTED = "cv_detector";
const REMOVABLE = new Set([CUSTOMER_MARKED, MODEL_DETECTED]);

// Outline colour while a detection's corners are being dragged — the same
// orange as its number badge.
const EDIT_COLOR = "#ea580c";

// One scan per roof per browser session: the scan is idempotent on the
// server (nothing already reviewed is offered again), but it costs
// ~10–15 s, so coming back to this screen shouldn't repeat it.
const scanKey = (checkId: string) => `obstacle-scan:${checkId}`;

function alreadyScanned(checkId: string): boolean {
  try {
    return window.sessionStorage.getItem(scanKey(checkId)) === "1";
  } catch {
    return false;
  }
}

function rememberScanned(checkId: string) {
  try {
    window.sessionStorage.setItem(scanKey(checkId), "1");
  } catch {
    /* private mode / storage blocked — the scan just repeats next visit */
  }
}

function NumberBadge({ n }: { n: number }) {
  return (
    <span
      className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white"
      style={{ background: EDIT_COLOR }}
      aria-hidden="true"
    >
      {n}
    </span>
  );
}

function TypePalette({
  value,
  onChange,
  disabled,
}: {
  value: ObstacleType;
  onChange: (type: ObstacleType) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {PALETTE.map((type) => {
        const { label, icon: Icon } = TYPE_META[type];
        const active = value === type;
        return (
          <button
            key={type}
            type="button"
            onClick={() => onChange(type)}
            aria-pressed={active}
            disabled={disabled}
            className={
              "flex items-center gap-1.5 rounded-[var(--radius-app)] border px-3 py-2 text-sm font-medium transition-colors disabled:opacity-60 " +
              (active
                ? "border-blue bg-surface-2 text-blue"
                : "border-line bg-paper text-ink-soft hover:border-blue hover:text-ink")
            }
          >
            <Icon size={15} strokeWidth={1.75} aria-hidden="true" />
            {label}
          </button>
        );
      })}
    </div>
  );
}

export function ObstacleMarkerClient({ check }: { check: Site }) {
  const router = useRouter();
  const { data, isLoading } = useCheckObstacles(check.id);
  const detect = useDetectCheckObstacles(check.id);
  const confirm = useConfirmCheckObstacle(check.id);
  const ignore = useIgnoreCheckObstacle(check.id);
  const mark = useMarkCheckObstacle(check.id);
  const unmark = useUnmarkCheckObstacle(check.id);

  const [selected, setSelected] = useState<ObstacleType>("water_tank");
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  // The detection being corrected, and its in-progress outline/type.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftOutline, setDraftOutline] = useState<{ lat: number; lng: number }[] | null>(null);
  const [draftType, setDraftType] = useState<ObstacleType>("other");

  const hasRoof = (check.boundary?.length ?? 0) >= 3;

  // Scan as soon as the customer lands here. The ref (not state) guards
  // against React strict mode running the effect twice in development.
  const startedScan = useRef(false);
  const scan = () => {
    setError(null);
    detect.mutate(undefined, {
      onSuccess: () => rememberScanned(check.id),
    });
  };
  useEffect(() => {
    if (!hasRoof || startedScan.current || alreadyScanned(check.id)) return;
    startedScan.current = true;
    scan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasRoof, check.id]);

  const scanning = detect.isPending;
  // The scan's own answer carries the reason when detection is unavailable.
  const scanResult = detect.data ?? null;
  const scanUnavailable =
    !scanning && (detect.isError || (scanResult !== null && scanResult.detected === false));
  const scanReason = scanResult?.reason ?? "Automatic detection isn't available right now.";

  // The lists come from ONE place — the obstacles query. A scan, a
  // confirm, an ignore and a removal all update that same query, so these
  // never go stale behind a cached scan response.
  const applied = data?.obstacles ?? [];
  const pending = data?.pending ?? [];
  const editing = pending.find((p) => p.id === editingId) ?? null;
  const busy =
    scanning ||
    confirm.isPending ||
    ignore.isPending ||
    mark.isPending ||
    unmark.isPending ||
    finishing;

  const fail = (fallback: string) => (err: unknown) =>
    setError(err instanceof Error ? err.message : fallback);

  const place = (lat: number, lng: number) => {
    if (scanning || editing) return;
    setError(null);
    mark.mutate({ type: selected, lat, lng }, { onError: fail("Couldn't save that. Please try tapping again.") });
  };

  const confirmOne = (obstacleId: string) => {
    setError(null);
    confirm.mutate({ obstacleId }, { onError: fail("Couldn't confirm that. Please try again.") });
  };

  const ignoreOne = (obstacleId: string) => {
    setError(null);
    ignore.mutate(obstacleId, { onError: fail("Couldn't dismiss that. Please try again.") });
  };

  const remove = (obstacleId: string) => {
    setError(null);
    unmark.mutate(obstacleId, { onError: fail("Couldn't remove that. Please try again.") });
  };

  const startEdit = (obstacleId: string) => {
    const target = pending.find((p) => p.id === obstacleId);
    if (!target) return;
    setError(null);
    setEditingId(obstacleId);
    setDraftOutline(target.polygon);
    setDraftType(target.type ?? "other");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setDraftOutline(null);
  };

  const saveEdit = () => {
    if (!editing) return;
    setError(null);
    confirm.mutate(
      {
        obstacleId: editing.id,
        edits: { type: draftType, ...(draftOutline ? { polygon: draftOutline } : {}) },
      },
      {
        onSuccess: cancelEdit,
        onError: fail("Couldn't save that. Check the outline sits on your roof and try again."),
      }
    );
  };

  const finish = () => {
    setError(null);
    setFinishing(true);
    // Confirmed obstacles are already applied to the roof (versioned as
    // they were confirmed/placed); anything still unreviewed is left out.
    // The processing screen runs the assessment against that geometry —
    // usable area, panel layout, system size, savings — shows its
    // progress, then lands on the result.
    router.push(`/check/${check.id}/processing`);
  };

  if (!hasRoof) {
    return (
      <div className="rounded-[var(--radius-app)] border border-dashed border-line bg-surface p-6 text-center">
        <p className="text-sm text-ink-soft">
          We haven&apos;t got a roof outline for this location yet, so there&apos;s nothing to scan
          or mark things on. A surveyor will record what&apos;s on the roof during the site visit.
        </p>
      </div>
    );
  }

  const scanFinishedClear =
    !scanning && !scanUnavailable && scanResult !== null && pending.length === 0 && applied.length === 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-ink">What&apos;s on your roof?</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">
          Water tanks, stair rooms, equipment — anything solar panels can&apos;t sit on. We scan your
          roof for these and you confirm what&apos;s real, then the panels go only on the space
          that&apos;s left.
        </p>
      </div>

      <div className="relative">
        <MapView
          // No pin: this map is about the roof, not the address. `center`
          // frames it without MapView drawing a location marker that the
          // customer might mistake for one of their own placements.
          pins={[]}
          center={{ lat: check.location.lat, lng: check.location.lng }}
          height="clamp(320px, 55dvh, 460px)"
          roofBoundary={check.boundary ?? undefined}
          roofObstacles={applied.map((o) => ({ id: o.id, polygon: o.polygon, number: o.number }))}
          // The detection being edited is drawn by the editor below instead.
          pendingRoofObstacles={pending
            .filter((o) => o.id !== editingId)
            .map((o) => ({ id: o.id, polygon: o.polygon, number: o.number }))}
          numberRoofObstacles
          interactive={!scanning && !editing}
          onMove={place}
          draggableCursor={editing ? undefined : "crosshair"}
          hint={
            scanning
              ? "Scanning your roof…"
              : editing
                ? "Drag the corners to fit the obstacle, then save."
                : pending.length > 0
                  ? "Dashed areas are waiting for your review."
                  : "Missed something? Pick what it is below, then tap it on the map."
          }
        >
          {editing && (
            <RoofBoundaryEditor
              key={editing.id}
              initial={editing.polygon}
              onChange={setDraftOutline}
              color={EDIT_COLOR}
              simplify={false}
            />
          )}
        </MapView>
        {scanning && (
          <div
            className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-[var(--radius-app)] text-center"
            style={{ background: "rgba(15, 23, 42, 0.55)" }}
            role="status"
            aria-live="polite"
          >
            <ScanSearch size={28} strokeWidth={1.75} className="text-white" aria-hidden="true" />
            <p className="text-sm font-medium text-white">Scanning your roof for obstacles…</p>
            <p className="flex items-center gap-1.5 text-xs text-white/80">
              <Loader2 size={13} className="animate-spin" aria-hidden="true" /> This takes about 15
              seconds
            </p>
          </div>
        )}
      </div>

      {/* Detection unavailable: say so, and offer another go. */}
      {!scanning && scanUnavailable && (
        <div className="flex items-start gap-2.5 rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2.5 text-sm text-ink-soft">
          <CircleHelp size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p>{scanReason} You can still mark anything on your roof yourself below.</p>
            <button
              type="button"
              onClick={scan}
              disabled={busy}
              className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-blue disabled:opacity-60"
            >
              <RefreshCw size={12} strokeWidth={1.75} aria-hidden="true" /> Scan again
            </button>
          </div>
        </div>
      )}
      {scanFinishedClear && (
        <p className="rounded-[var(--radius-app)] border border-line bg-surface px-3 py-2.5 text-sm text-ink-soft">
          We didn&apos;t spot anything on your roof. If it really is clear, that&apos;s good news —
          just continue.
        </p>
      )}

      {/* The review list: AI detections waiting for the customer. */}
      {pending.length > 0 && (
        <div
          className="rounded-[var(--radius-app)] border px-4 py-3.5"
          style={{ background: "var(--warn-bg)", borderColor: "var(--amber-soft)" }}
        >
          <p
            className="flex items-start gap-2 text-sm font-semibold leading-snug"
            style={{ color: "var(--warn)" }}
          >
            <Sparkles size={16} strokeWidth={1.75} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              {pending.length} AI-detected {pending.length === 1 ? "obstacle needs" : "obstacles need"}{" "}
              review — none count toward panel placement or shading until confirmed.
            </span>
          </p>
          <ul className="mt-3 space-y-3 pl-0 sm:pl-6">
            {pending.map((obstacle) => {
              const percent =
                obstacle.confidence !== null ? `${Math.round(obstacle.confidence * 100)}%` : null;
              const isEditing = editingId === obstacle.id;
              return (
                <li key={obstacle.id}>
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <span className="rounded-full bg-surface-2 px-3.5 py-2 text-sm font-medium text-ink">
                      #{obstacle.number ?? "–"} Detected obstacle
                      {percent ? ` · ${percent} confidence` : ""}
                    </span>
                    {!isEditing && (
                      <>
                        <Button
                          onClick={() => confirmOne(obstacle.id)}
                          disabled={busy}
                          className="px-6 font-semibold"
                        >
                          Confirm
                        </Button>
                        <button
                          type="button"
                          onClick={() => startEdit(obstacle.id)}
                          disabled={busy}
                          className="text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-60"
                          style={{ color: "var(--amber)" }}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => ignoreOne(obstacle.id)}
                          disabled={busy}
                          className="text-sm font-medium transition-opacity hover:opacity-80 disabled:opacity-60"
                          style={{ color: "var(--bad)" }}
                        >
                          Ignore
                        </button>
                      </>
                    )}
                  </div>

                  {isEditing && (
                    <div className="mt-3 space-y-3 rounded-[var(--radius-app)] border border-line bg-paper p-3">
                      <p className="text-xs text-ink-soft">
                        Pick what it is, then drag its corners on the map so the orange outline fits
                        it.
                      </p>
                      <TypePalette value={draftType} onChange={setDraftType} disabled={busy} />
                      <div className="flex flex-wrap items-center gap-3">
                        <Button onClick={saveEdit} disabled={busy} className="px-5 font-semibold">
                          {confirm.isPending ? (
                            <>
                              <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Saving…
                            </>
                          ) : (
                            "Save & confirm"
                          )}
                        </Button>
                        <button
                          type="button"
                          onClick={cancelEdit}
                          disabled={busy}
                          className="text-sm font-medium text-ink-soft hover:text-ink disabled:opacity-60"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Confirmed obstacles, and ones the customer added themselves. */}
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          Kept clear of panels
        </p>
        {isLoading && !data ? (
          <p className="flex items-center gap-1.5 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Loading…
          </p>
        ) : applied.length === 0 ? (
          <p className="rounded-[var(--radius-app)] border border-dashed border-line bg-surface px-3 py-3 text-sm text-ink-soft">
            {scanning
              ? "Looking…"
              : pending.length > 0
                ? "Nothing yet — confirm an obstacle above, and the panels will avoid it."
                : "Nothing marked."}
          </p>
        ) : (
          <ul className="space-y-2.5">
            {applied.map((obstacle) => {
              const meta = obstacle.type ? TYPE_META[obstacle.type] : null;
              const Icon = meta?.icon ?? CircleHelp;
              const removable = obstacle.source !== null && REMOVABLE.has(obstacle.source);
              const origin =
                obstacle.source === MODEL_DETECTED
                  ? "Confirmed by you"
                  : obstacle.source === CUSTOMER_MARKED
                    ? "Added by you"
                    : "We spotted this one";
              return (
                <li key={obstacle.id} className="flex items-center gap-2.5 text-sm">
                  {obstacle.number !== null && <NumberBadge n={obstacle.number} />}
                  <span
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-app)]"
                    style={{ background: "var(--surface-2)", color: "var(--amber)" }}
                    aria-hidden="true"
                  >
                    <Icon size={14} strokeWidth={1.75} />
                  </span>
                  <span className="text-ink">{meta?.label ?? "Something on the roof"}</span>
                  <span className="text-xs text-ink-faint">{origin}</span>
                  {removable && (
                    <button
                      type="button"
                      onClick={() => remove(obstacle.id)}
                      disabled={busy}
                      aria-label={`Remove ${meta?.label ?? "this obstacle"}`}
                      className="ml-auto inline-flex items-center gap-1 rounded-[var(--radius-app)] px-2 py-1 text-xs text-ink-faint transition-colors hover:text-[var(--bad)] disabled:opacity-60"
                    >
                      <Trash2 size={13} strokeWidth={1.75} aria-hidden="true" /> Remove
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Add anything the scan missed. */}
      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">
          Missed something? Pick what it is, then tap it on the map
        </p>
        <TypePalette value={selected} onChange={setSelected} disabled={busy || !!editing} />
      </div>

      {error && (
        <p
          className="rounded-[var(--radius-app)] border px-3 py-2 text-xs"
          role="alert"
          style={{ borderColor: "var(--bad)", color: "var(--bad)" }}
        >
          {error}
        </p>
      )}

      <Button className="w-full" onClick={finish} disabled={busy || !!editing}>
        {finishing ? (
          <>
            <Loader2 size={16} className="animate-spin" aria-hidden="true" /> Starting your
            assessment…
          </>
        ) : (
          <>
            Continue <ArrowRight size={16} strokeWidth={1.75} aria-hidden="true" />
          </>
        )}
      </Button>

      <p className="text-xs text-ink-faint">
        Only obstacles you&apos;ve confirmed are kept clear of the panels, so your panel count and
        savings are calculated from what&apos;s really up there.
        {pending.length > 0 &&
          ` ${pending.length} ${pending.length === 1 ? "detection is" : "detections are"} still waiting for your review and will be left out.`}
      </p>
    </div>
  );
}
