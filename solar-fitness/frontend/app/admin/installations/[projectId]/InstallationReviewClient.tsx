"use client";

// The admin's two gates over one installation project: approve the
// vendor's QC checklist, then approve commissioning (which is also what
// marks the project completed — nothing else does). Same
// panel-per-decision shape as AssessmentReviewClient.tsx, including its
// local-state disclosure for a destructive-ish confirm rather than a
// route change.

import { CheckCircle2, ClipboardCheck, ShieldCheck, Zap } from "lucide-react";
import {
  useAdminCommissioning,
  useAdminInstallation,
  useAdminInstallationPhotos,
  useAdminInstallationQc,
  useApproveCommissioning,
  useApproveInstallationQc,
  useSetAdminInstallationStatus,
} from "@/lib/query/hooks";
import { Badge, Button, Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import { StageProgress, stageLabel } from "@/components/installations/StageProgress";
import { QC_CHECKLIST_ITEMS, QC_CHECKLIST_LABEL } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

export function InstallationReviewClient({ projectId }: { projectId: string }) {
  const project = useAdminInstallation(projectId);
  const qc = useAdminInstallationQc(projectId);
  const commissioning = useAdminCommissioning(projectId);
  const photos = useAdminInstallationPhotos(projectId);
  const setStatus = useSetAdminInstallationStatus(projectId);
  const approveQc = useApproveInstallationQc(projectId);
  const approveCommissioning = useApproveCommissioning(projectId);

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
  const record = commissioning.data;
  const qcSubmitted = qc.data?.submittedAt != null;
  const qcApproved = qc.data?.approvedAt != null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        <Card className="p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-3">
              <span
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-teal"
                style={{ background: "var(--teal-soft, rgba(20,148,132,0.12))" }}
                aria-hidden="true"
              >
                <Zap size={19} strokeWidth={1.75} />
              </span>
              <div>
                <h1 className="text-lg font-semibold text-ink">
                  {p.approvedCapacityKwp} kWp installation
                </h1>
                <p className="mt-0.5 text-xs text-ink-soft">
                  Site {p.siteId.slice(0, 8)} · opened {formatDateTime(p.createdAt)}
                </p>
              </div>
            </div>
            <Badge tone={p.status === "completed" ? "blue" : "neutral"}>
              {stageLabel(p.status)}
            </Badge>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-line pt-4 sm:grid-cols-3">
            <Stat label="Panel model" value={p.panelModel ?? "Not recorded"} />
            <Stat label="Inverter model" value={p.inverterModel ?? "Not recorded"} />
            <Stat
              label="Assigned vendor"
              value={p.assignedVendorId ? p.assignedVendorId.slice(0, 8) : "Unassigned"}
            />
          </dl>
        </Card>

        {/* --- QC gate --- */}
        <Card className="space-y-4 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              <ClipboardCheck size={15} strokeWidth={1.75} aria-hidden="true" />
              Quality checklist
            </h2>
            <Badge tone={qcApproved ? "blue" : qcSubmitted ? "amber" : "neutral"}>
              {qcApproved ? "Approved" : qcSubmitted ? "Awaiting approval" : "Not submitted"}
            </Badge>
          </div>

          <ul className="grid grid-cols-1 gap-1 sm:grid-cols-2">
            {QC_CHECKLIST_ITEMS.map((key) => {
              const value = qc.data?.checklist?.[key] ?? null;
              return (
                <li
                  key={key}
                  className="flex items-center justify-between gap-2 rounded-[var(--radius-app)] px-2 py-1.5 text-sm hover:bg-surface-2"
                >
                  <span className="text-ink">{QC_CHECKLIST_LABEL[key] ?? key}</span>
                  <Badge tone={value === true ? "blue" : value === false ? "red" : "neutral"}>
                    {value === true ? "Pass" : value === false ? "Fail" : "Not inspected"}
                  </Badge>
                </li>
              );
            })}
          </ul>

          {qc.data?.notes && (
            <p className="rounded-[var(--radius-app)] bg-surface-2 px-3 py-2 text-sm text-ink-soft">
              {qc.data.notes}
            </p>
          )}

          <div className="border-t border-line pt-3">
            {qcApproved ? (
              <p className="text-xs text-ink-faint">
                Approved {qc.data?.approvedAt ? formatDateTime(qc.data.approvedAt) : ""}
                {qc.data?.approvedBy ? ` by ${qc.data.approvedBy}` : ""}.
              </p>
            ) : (
              <>
                <Button
                  size="sm"
                  disabled={!qcSubmitted || approveQc.isPending}
                  onClick={() => approveQc.mutate()}
                >
                  <CheckCircle2 size={14} strokeWidth={1.75} />
                  {approveQc.isPending ? "Approving…" : "Approve checklist"}
                </Button>
                {!qcSubmitted && (
                  <p className="mt-2 text-xs text-ink-faint">
                    The vendor has not submitted the checklist yet — there is nothing to approve.
                  </p>
                )}
              </>
            )}
          </div>
        </Card>

        {/* --- commissioning gate --- */}
        <Card className="space-y-4 p-4">
          <div className="flex items-center justify-between gap-2">
            <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              <ShieldCheck size={15} strokeWidth={1.75} aria-hidden="true" />
              Commissioning
            </h2>
            <Badge
              tone={
                record?.adminApproved ? "blue" : record?.vendorConfirmed ? "amber" : "neutral"
              }
            >
              {record?.adminApproved
                ? "Approved"
                : record?.vendorConfirmed
                  ? "Awaiting approval"
                  : "Not submitted"}
            </Badge>
          </div>

          {record ? (
            <>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Stat
                  label="Installed capacity"
                  value={record.installedCapacityKwp != null ? `${record.installedCapacityKwp} kWp` : "—"}
                />
                <Stat label="Panel count" value={String(record.installedPanelCount ?? "—")} />
                <Stat label="Inverter serial" value={record.inverterSerialNumber ?? "—"} />
                <Stat label="Meter number" value={record.meterNumber ?? "—"} />
                <Stat
                  label="Voltage"
                  value={record.voltageReading != null ? `${record.voltageReading} V` : "—"}
                />
                <Stat
                  label="Current"
                  value={record.currentReading != null ? `${record.currentReading} A` : "—"}
                />
              </dl>
              <div className="flex flex-wrap gap-2">
                <Badge tone={record.earthingTestPassed ? "blue" : "neutral"}>
                  Earthing test:{" "}
                  {record.earthingTestPassed == null
                    ? "not tested"
                    : record.earthingTestPassed
                      ? "passed"
                      : "failed"}
                </Badge>
                <Badge tone={record.insulationTestPassed ? "blue" : "neutral"}>
                  Insulation test:{" "}
                  {record.insulationTestPassed == null
                    ? "not tested"
                    : record.insulationTestPassed
                      ? "passed"
                      : "failed"}
                </Badge>
                <Badge tone={record.customerAccepted ? "blue" : "amber"}>
                  Customer {record.customerAccepted ? "accepted" : "has not accepted"}
                </Badge>
              </div>
              {record.panelSerialNumbers.length > 0 && (
                <p className="text-xs text-ink-soft">
                  Panel serials: {record.panelSerialNumbers.join(", ")}
                </p>
              )}
            </>
          ) : (
            <p className="text-sm text-ink-faint">
              The vendor has not submitted a commissioning record for this project yet.
            </p>
          )}

          <div className="border-t border-line pt-3">
            {record?.adminApproved ? (
              <p className="text-xs text-ink-faint">
                Approved
                {record.commissioningDate ? ` on ${formatDateTime(record.commissioningDate)}` : ""} —
                the project is complete.
              </p>
            ) : (
              <>
                <Button
                  size="sm"
                  disabled={!record?.vendorConfirmed || approveCommissioning.isPending}
                  onClick={() => approveCommissioning.mutate()}
                >
                  <CheckCircle2 size={14} strokeWidth={1.75} />
                  {approveCommissioning.isPending ? "Approving…" : "Approve & complete project"}
                </Button>
                <p className="mt-2 text-xs text-ink-faint">
                  Approving marks the project completed. It cannot be edited by the vendor afterwards.
                </p>
              </>
            )}
          </div>
        </Card>

        {photos.data && photos.data.length > 0 && (
          <Card className="space-y-3 p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Progress photos
            </h2>
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {photos.data.map((photo) => (
                <li
                  key={photo.id}
                  className="overflow-hidden rounded-[var(--radius-app)] border border-line"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={photo.dataUrl}
                    alt={`${stageLabel(photo.stage)} progress`}
                    className="h-24 w-full object-cover"
                  />
                  <div className="px-2 py-1.5">
                    <p className="truncate text-[11px] font-medium text-ink">
                      {stageLabel(photo.stage)}
                    </p>
                    <p className="truncate text-[11px] text-ink-faint">
                      {photo.lat != null && photo.lng != null
                        ? `${photo.lat.toFixed(4)}, ${photo.lng.toFixed(4)}`
                        : "No location"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <Card className="space-y-4 p-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Stage</h2>
          <StageProgress
            stages={p.stages}
            stageIndex={p.stageIndex}
            className="max-h-[24rem] overflow-y-auto scrollbar-thin pr-1"
          />
          <div className="border-t border-line pt-3">
            <label className="block text-xs text-ink-soft" htmlFor="admin-stage">
              Override stage
            </label>
            <select
              id="admin-stage"
              value={p.status}
              onChange={(e) => setStatus.mutate({ status: e.target.value })}
              className="mt-1 w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink outline-none focus:border-teal"
            >
              {p.stages.map((s) => (
                <option key={s} value={s}>
                  {stageLabel(s)}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-ink-faint">
              An override can move the project backwards — use it to correct a mis-tapped stage, not
              to skip work.
            </p>
          </div>
        </Card>
      </div>
    </div>
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
