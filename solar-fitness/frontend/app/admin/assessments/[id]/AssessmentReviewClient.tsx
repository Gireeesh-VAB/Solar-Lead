"use client";

import { useState } from "react";
import Link from "next/link";
import {
  useAdminAssessment,
  useApproveAssessment,
  useRejectAssessment,
  useAdminVendors,
  useSaveGridFeasibility,
  useSaveFinancialFeasibility,
} from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Button, Badge } from "@/components/ui/Primitives";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { ConfidenceMeter } from "@/components/ui/ConfidenceMeter";
import { formatDate, formatDateTime, formatKwp } from "@/lib/utils";
import { CheckCircle2, XCircle, ShieldCheck, Clock, ExternalLink } from "lucide-react";
import type { FinancialFeasibility, GridConnectionStatus, GridFeasibility, ReviewStatus } from "@/lib/api/client";

const REVIEW_STATUS_LABEL: Record<ReviewStatus, string> = {
  pending: "Pending admin review",
  approved: "Approved — vendor assigned",
  rejected: "Rejected",
  not_applicable: "Not applicable",
};

const GRID_STATUS_LABEL: Record<GridConnectionStatus, string> = {
  not_started: "Not started",
  application_submitted: "Application submitted",
  under_review: "Under review",
  approved: "Approved",
  connected: "Connected",
  rejected: "Rejected",
};

const EMPTY_GRID_FEASIBILITY: GridFeasibility = { gridConnectionStatus: "not_started" };
const EMPTY_FINANCIAL_FEASIBILITY: FinancialFeasibility = {};

const COST_FIELDS: { key: keyof FinancialFeasibility; label: string }[] = [
  { key: "panelCostInr", label: "Panels" },
  { key: "inverterCostInr", label: "Inverter" },
  { key: "mountingStructureCostInr", label: "Mounting structure" },
  { key: "dcCableCostInr", label: "DC cables" },
  { key: "acCableCostInr", label: "AC cables" },
  { key: "protectionEquipmentCostInr", label: "Protection equipment" },
  { key: "installationCostInr", label: "Installation" },
  { key: "civilWorkCostInr", label: "Civil work" },
  { key: "transportationCostInr", label: "Transportation" },
  { key: "otherChargesInr", label: "Other charges" },
];

const CHECK_STATUS_LABEL: Record<string, string> = {
  ok: "Passed",
  estimated: "Estimated",
  insufficient_data: "Insufficient data",
  not_applicable: "Not applicable",
};

const CHECK_KIND_LABEL: Record<string, string> = {
  physical: "Site, roof & structural",
  regulatory: "Electrical & regulatory",
  commercial: "Commercial viability",
};

function statusTone(status: string): "neutral" | "blue" | "amber" {
  if (status === "ok") return "blue";
  if (status === "estimated") return "amber";
  return "neutral";
}

function FinancialFeasibilitySection({ assessmentId, initial }: { assessmentId: string; initial: FinancialFeasibility | null }) {
  const save = useSaveFinancialFeasibility(assessmentId);
  const [f, setF] = useState<FinancialFeasibility>(initial ?? EMPTY_FINANCIAL_FEASIBILITY);
  const set = <K extends keyof FinancialFeasibility>(key: K, value: FinancialFeasibility[K]) => setF((prev) => ({ ...prev, [key]: value }));

  const computedTotal = COST_FIELDS.reduce((sum, { key }) => sum + (f[key] as number | null | undefined ?? 0), 0);

  return (
    <Card className="p-4 space-y-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Financial feasibility</h2>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">System cost (₹)</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {COST_FIELDS.map(({ key, label }) => (
            <div key={key}>
              <label className="mb-1 block text-xs text-ink-faint">{label}</label>
              <input
                type="number"
                min={0}
                value={(f[key] as number | null | undefined) ?? ""}
                onChange={(e) => set(key, (e.target.value ? Number(e.target.value) : null) as FinancialFeasibility[typeof key])}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              />
            </div>
          ))}
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Total project cost (computed: ₹{computedTotal.toLocaleString("en-IN")})</label>
            <input
              type="number"
              min={0}
              placeholder={computedTotal ? String(computedTotal) : "Auto"}
              value={f.totalProjectCostInr ?? ""}
              onChange={(e) => set("totalProjectCostInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">Subsidy</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <label className="flex items-center gap-2 pt-5 text-sm text-ink">
            <input type="checkbox" checked={f.subsidyApplicable ?? false} onChange={(e) => set("subsidyApplicable", e.target.checked)} />
            Subsidy applicable
          </label>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Subsidy category</label>
            <input
              value={f.subsidyCategory ?? ""}
              onChange={(e) => set("subsidyCategory", e.target.value)}
              placeholder="e.g. PM Surya Ghar"
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Subsidy amount (₹)</label>
            <input
              type="number"
              min={0}
              value={f.subsidyAmountInr ?? ""}
              onChange={(e) => set("subsidyAmountInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Customer contribution (₹)</label>
            <input
              type="number"
              min={0}
              value={f.customerContributionInr ?? ""}
              onChange={(e) => set("customerContributionInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-faint">ROI</h3>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Monthly savings (₹)</label>
            <input
              type="number"
              min={0}
              value={f.monthlySavingsInr ?? ""}
              onChange={(e) => set("monthlySavingsInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Annual savings (₹)</label>
            <input
              type="number"
              min={0}
              value={f.annualSavingsInr ?? ""}
              onChange={(e) => set("annualSavingsInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Payback period (years)</label>
            <input
              type="number"
              min={0}
              value={f.paybackPeriodYears ?? ""}
              onChange={(e) => set("paybackPeriodYears", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">10-year savings (₹)</label>
            <input
              type="number"
              min={0}
              value={f.tenYearSavingsInr ?? ""}
              onChange={(e) => set("tenYearSavingsInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">20-year savings (₹)</label>
            <input
              type="number"
              min={0}
              value={f.twentyYearSavingsInr ?? ""}
              onChange={(e) => set("twentyYearSavingsInr", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-ink-faint">Est. system lifetime (years)</label>
            <input
              type="number"
              min={0}
              value={f.estimatedSystemLifetimeYears ?? ""}
              onChange={(e) => set("estimatedSystemLifetimeYears", e.target.value ? Number(e.target.value) : null)}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
          </div>
        </div>
      </div>

      <div>
        <label className="mb-1 block text-xs text-ink-faint">Notes</label>
        <textarea
          value={f.notes ?? ""}
          onChange={(e) => set("notes", e.target.value)}
          rows={2}
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
        />
      </div>
      {save.isError && <p className="text-xs text-bad">{(save.error as Error).message}</p>}
      <Button size="sm" onClick={() => save.mutate(f)} disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save financial feasibility"}
      </Button>
    </Card>
  );
}

function GridFeasibilitySection({ assessmentId, initial }: { assessmentId: string; initial: GridFeasibility | null }) {
  const save = useSaveGridFeasibility(assessmentId);
  const [g, setG] = useState<GridFeasibility>(initial ?? EMPTY_GRID_FEASIBILITY);
  const set = <K extends keyof GridFeasibility>(key: K, value: GridFeasibility[K]) => setG((prev) => ({ ...prev, [key]: value }));

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Grid / DISCOM feasibility</h2>
        <Badge tone={g.gridConnectionStatus === "connected" || g.gridConnectionStatus === "approved" ? "blue" : "neutral"}>
          {GRID_STATUS_LABEL[g.gridConnectionStatus]}
        </Badge>
      </div>
      <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
        <div>
          <label className="mb-1 block text-xs text-ink-faint">DISCOM</label>
          <input
            value={g.discom ?? ""}
            onChange={(e) => set("discom", e.target.value)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Distribution area</label>
          <input
            value={g.distributionArea ?? ""}
            onChange={(e) => set("distributionArea", e.target.value)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Connection status</label>
          <select
            value={g.gridConnectionStatus}
            onChange={(e) => set("gridConnectionStatus", e.target.value as GridConnectionStatus)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          >
            {(Object.keys(GRID_STATUS_LABEL) as GridConnectionStatus[]).map((st) => (
              <option key={st} value={st}>
                {GRID_STATUS_LABEL[st]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Transformer capacity (kVA)</label>
          <input
            type="number"
            min={0}
            value={g.transformerCapacityKva ?? ""}
            onChange={(e) => set("transformerCapacityKva", e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Max permissible capacity (kWp)</label>
          <input
            type="number"
            min={0}
            value={g.maxPermissibleCapacityKwp ?? ""}
            onChange={(e) => set("maxPermissibleCapacityKwp", e.target.value ? Number(e.target.value) : null)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-ink-faint">Application reference</label>
          <input
            value={g.applicationReference ?? ""}
            onChange={(e) => set("applicationReference", e.target.value)}
            className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
          />
        </div>
      </div>
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={g.netMeteringAvailable ?? false} onChange={(e) => set("netMeteringAvailable", e.target.checked)} />
          Net metering available
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={g.grossMeteringAvailable ?? false} onChange={(e) => set("grossMeteringAvailable", e.target.checked)} />
          Gross metering available
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={g.applicationRequired ?? false} onChange={(e) => set("applicationRequired", e.target.checked)} />
          Application required
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input type="checkbox" checked={g.gridApprovalRequired ?? false} onChange={(e) => set("gridApprovalRequired", e.target.checked)} />
          Grid approval required
        </label>
      </div>
      <div>
        <label className="mb-1 block text-xs text-ink-faint">Notes</label>
        <textarea
          value={g.notes ?? ""}
          onChange={(e) => set("notes", e.target.value)}
          rows={2}
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
        />
      </div>
      {save.isError && <p className="text-xs text-bad">{(save.error as Error).message}</p>}
      <Button size="sm" onClick={() => save.mutate(g)} disabled={save.isPending}>
        {save.isPending ? "Saving…" : "Save grid feasibility"}
      </Button>
    </Card>
  );
}

export function AssessmentReviewClient({ assessmentId }: { assessmentId: string }) {
  const assessment = useAdminAssessment(assessmentId);
  const approve = useApproveAssessment(assessmentId);
  const reject = useRejectAssessment(assessmentId);
  const vendors = useAdminVendors({ verificationStatus: "verified" });

  const [vendorId, setVendorId] = useState("");
  const [panelWattage, setPanelWattage] = useState(550);
  const [deadlineDays, setDeadlineDays] = useState(3);
  const [payoutInr, setPayoutInr] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [showReject, setShowReject] = useState(false);

  if (assessment.isLoading) return <CardSkeleton className="h-96" />;
  if (assessment.isError || !assessment.data) {
    return <ErrorState description="Could not load this assessment." onRetry={() => assessment.refetch()} />;
  }

  const a = assessment.data;
  const groups: Record<string, typeof a.checklist> = {};
  for (const item of a.checklist) {
    (groups[item.kind] ??= []).push(item);
  }

  const isPending = a.reviewStatus === "pending";

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        <Card className="p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-semibold text-ink">{a.siteName}</h2>
              <p className="text-sm text-ink-soft">
                {a.address ? `${a.address} · ` : ""}
                {a.district}
                {a.district && a.state ? ", " : ""}
                {a.state}
              </p>
              <p className="font-mono tabular text-xs text-ink-faint">{a.siteId}</p>
            </div>
            <VerdictChip verdict={a.assessment.verdict} size="lg" />
          </div>
          <div className="grid grid-cols-2 gap-3 border-t border-line pt-3 text-sm sm:grid-cols-4">
            <div>
              <p className="text-xs text-ink-faint">Recommended capacity</p>
              <p className="font-mono tabular text-ink">
                {a.assessment.capacityKwp > 0 ? formatKwp(a.assessment.capacityKwp) : "—"}
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Confidence</p>
              <ConfidenceMeter tier={a.assessment.confidence} />
            </div>
            <div>
              <p className="text-xs text-ink-faint">Binding constraint</p>
              <p className="text-ink">{a.assessment.bindingConstraint?.name ?? "—"}</p>
            </div>
            <div>
              <p className="text-xs text-ink-faint">Assessed</p>
              <p className="font-mono tabular text-ink">{formatDate(a.assessment.assessedAt)}</p>
            </div>
          </div>
        </Card>

        <Card className="p-4 space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">
            Feasibility checklist ({a.checklist.length} checks evaluated)
          </h2>
          {a.checklist.length === 0 && (
            <p className="text-sm text-ink-soft">No per-constraint checklist was recorded for this assessment.</p>
          )}
          {Object.entries(groups).map(([kind, items]) => (
            <div key={kind} className="space-y-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
                {CHECK_KIND_LABEL[kind] ?? kind}
              </h3>
              <div className="space-y-2">
                {items.map((item, i) => (
                  <div
                    key={`${item.label}-${i}`}
                    className="flex items-start justify-between gap-3 rounded-[var(--radius-app)] border border-line px-3 py-2"
                  >
                    <div>
                      <p className="flex items-center gap-2 text-sm font-medium text-ink">
                        {item.label}
                        {item.isBinding && <Badge tone="amber">Binding</Badge>}
                      </p>
                      {item.note && <p className="mt-0.5 text-xs text-ink-soft">{item.note}</p>}
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      {item.kwp != null && (
                        <span className="font-mono tabular text-sm text-ink">{formatKwp(item.kwp)}</span>
                      )}
                      <Badge tone={statusTone(item.status)}>{CHECK_STATUS_LABEL[item.status] ?? item.status}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </Card>

        {a.assessment.capacityKwp > 0 && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">System sizing</h2>
            <div className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-xs text-ink-faint">Proposed DC capacity</p>
                <p className="font-mono tabular text-ink">{formatKwp(a.assessment.capacityKwp)}</p>
              </div>
              <div>
                <label htmlFor="panel-wattage" className="text-xs text-ink-faint">
                  Panel wattage (W)
                </label>
                <input
                  id="panel-wattage"
                  type="number"
                  min={100}
                  step={10}
                  value={panelWattage}
                  onChange={(e) => setPanelWattage(Number(e.target.value) || 550)}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1 font-mono tabular text-sm text-ink"
                />
              </div>
              <div>
                <p className="text-xs text-ink-faint">Estimated panel count</p>
                <p className="font-mono tabular text-ink">
                  {panelWattage > 0 ? Math.ceil((a.assessment.capacityKwp * 1000) / panelWattage) : "—"}
                </p>
              </div>
              <div>
                <p className="text-xs text-ink-faint">Inverter capacity (1.2 DC:AC)</p>
                <p className="font-mono tabular text-ink">{(a.assessment.capacityKwp / 1.2).toFixed(1)} kW</p>
              </div>
            </div>
            {a.assessment.generation ? (
              <div className="grid grid-cols-2 gap-3 border-t border-line pt-3 text-sm sm:grid-cols-3">
                <div>
                  <p className="text-xs text-ink-faint">Estimated annual generation</p>
                  <p className="font-mono tabular text-ink">
                    {a.assessment.generation.estimatedKwhPerYear != null
                      ? `${Math.round(a.assessment.generation.estimatedKwhPerYear).toLocaleString("en-IN")} kWh`
                      : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Performance ratio</p>
                  <p className="font-mono tabular text-ink">
                    {a.assessment.generation.performanceRatio != null ? `${Math.round(a.assessment.generation.performanceRatio * 100)}%` : "—"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Specific yield</p>
                  <p className="font-mono tabular text-ink">
                    {a.assessment.generation.specificYieldKwhPerKwp != null
                      ? `${Math.round(a.assessment.generation.specificYieldKwhPerKwp)} kWh/kWp`
                      : "—"}
                  </p>
                </div>
                <p className="col-span-full text-xs text-ink-faint">Method: {a.assessment.generation.method}</p>
              </div>
            ) : (
              <p className="border-t border-line pt-3 text-xs text-ink-faint">No generation estimate available for this assessment.</p>
            )}
          </Card>
        )}

        <GridFeasibilitySection assessmentId={assessmentId} initial={a.gridFeasibility} />
        <FinancialFeasibilitySection assessmentId={assessmentId} initial={a.financialFeasibility} />

        {a.assessment.reasons.length > 0 && (
          <Card className="p-4 space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Engine notes</h2>
            <ul className="list-inside list-disc space-y-1 text-sm text-ink-soft">
              {a.assessment.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <div className="space-y-4">
        <Card className="p-4 space-y-3">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Review status</h2>
          <div className="flex items-center gap-2">
            {a.reviewStatus === "approved" && <ShieldCheck size={16} className="text-good" strokeWidth={1.75} />}
            {a.reviewStatus === "rejected" && <XCircle size={16} className="text-bad" strokeWidth={1.75} />}
            {a.reviewStatus === "pending" && <Clock size={16} className="text-amber" strokeWidth={1.75} />}
            <p className="text-sm font-medium text-ink">{REVIEW_STATUS_LABEL[a.reviewStatus]}</p>
          </div>
          {a.reviewedBy && a.reviewedAt && (
            <p className="text-xs text-ink-faint">
              by {a.reviewedBy} · {formatDateTime(a.reviewedAt)}
            </p>
          )}
          {a.reviewStatus === "rejected" && a.rejectionReason && (
            <p className="rounded-[var(--radius-app)] bg-surface-2 p-2 text-sm text-ink-soft">{a.rejectionReason}</p>
          )}
          {a.reviewStatus === "approved" && a.vendorJobId && (
            <Link
              href={`/admin/vendors/${a.assignedVendorId}`}
              className="inline-flex items-center gap-1 text-sm font-medium text-blue hover:underline"
            >
              View assigned vendor <ExternalLink size={14} strokeWidth={1.75} />
            </Link>
          )}
        </Card>

        {isPending && !showReject && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Approve &amp; assign vendor</h2>
            <div>
              <label htmlFor="vendor-select" className="mb-1 block text-xs text-ink-faint">
                Vendor
              </label>
              <select
                id="vendor-select"
                value={vendorId}
                onChange={(e) => setVendorId(e.target.value)}
                className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
              >
                <option value="">Select a verified vendor…</option>
                {(vendors.data ?? []).map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name} · {v.serviceArea}
                  </option>
                ))}
              </select>
              {vendors.data && vendors.data.length === 0 && (
                <p className="mt-1 text-xs text-ink-faint">No verified vendors yet — verify one first.</p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="deadline-days" className="mb-1 block text-xs text-ink-faint">
                  Survey deadline (days)
                </label>
                <input
                  id="deadline-days"
                  type="number"
                  min={1}
                  max={30}
                  value={deadlineDays}
                  onChange={(e) => setDeadlineDays(Number(e.target.value))}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
                />
              </div>
              <div>
                <label htmlFor="payout-inr" className="mb-1 block text-xs text-ink-faint">
                  Payout ₹ (optional)
                </label>
                <input
                  id="payout-inr"
                  type="number"
                  min={0}
                  placeholder="Auto"
                  value={payoutInr}
                  onChange={(e) => setPayoutInr(e.target.value)}
                  className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
                />
              </div>
            </div>
            {approve.isError && <p className="text-xs text-bad">{(approve.error as Error).message}</p>}
            <div className="flex gap-2">
              <Button
                className="flex-1"
                disabled={!vendorId || approve.isPending}
                onClick={() =>
                  approve.mutate({
                    vendorId,
                    deadlineDays,
                    payoutInr: payoutInr ? Number(payoutInr) : undefined,
                  })
                }
              >
                <CheckCircle2 size={14} strokeWidth={1.75} />
                {approve.isPending ? "Approving…" : "Approve & assign"}
              </Button>
              <Button variant="secondary" onClick={() => setShowReject(true)}>
                Reject
              </Button>
            </div>
          </Card>
        )}

        {isPending && showReject && (
          <Card className="p-4 space-y-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">Reject this assessment</h2>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Reason the admin team is rejecting this site…"
              rows={4}
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
            />
            {reject.isError && <p className="text-xs text-bad">{(reject.error as Error).message}</p>}
            <div className="flex gap-2">
              <Button
                variant="danger"
                className="flex-1"
                disabled={!rejectReason.trim() || reject.isPending}
                onClick={() => reject.mutate(rejectReason.trim())}
              >
                <XCircle size={14} strokeWidth={1.75} />
                {reject.isPending ? "Rejecting…" : "Confirm reject"}
              </Button>
              <Button variant="secondary" onClick={() => setShowReject(false)}>
                Back
              </Button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
