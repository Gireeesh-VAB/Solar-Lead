import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { CalendarClock, ListChecks, MapPin, Home, Zap, BatteryCharging } from "lucide-react";
import { getVendorJobServer as getVendorJob, getSiteServer as getSite, orRedirectToLogin } from "@/lib/api/serverFetch";
import { Card, PageHeader } from "@/components/ui/Primitives";
import { SlaBadge } from "@/components/vendor/SlaBadge";
import { siteTypeLabel, formatDate } from "@/lib/utils";
import type { ConnectionType, RoofMaterial, RoofSlope, RoofType } from "@/lib/types";
import { JobActions } from "./JobActions";
import { ObstacleSurveySection } from "./ObstacleSurveySection";
import { StructuralAssessmentSection } from "./StructuralAssessmentSection";
import { ElectricalAssessmentSection } from "./ElectricalAssessmentSection";
import { InstallationConstraintsSection } from "./InstallationConstraintsSection";
import { SafetyAssessmentSection } from "./SafetyAssessmentSection";
import { BatteryAssessmentSection } from "./BatteryAssessmentSection";

const CONNECTION_TYPE_LABEL: Record<ConnectionType, string> = {
  SINGLE_PHASE: "Single phase",
  THREE_PHASE: "Three phase",
};

const ROOF_TYPE_LABEL: Record<RoofType, string> = {
  RCC_CONCRETE: "RCC / concrete",
  METAL_SHEET: "Metal sheet",
  GI_SHEET: "GI sheet",
  TILED: "Tiled roof",
  ASBESTOS_SHEET: "Asbestos sheet",
  GROUND_MOUNTED: "Ground-mounted",
  TERRACE: "Terrace",
  OTHER: "Other",
};
const ROOF_MATERIAL_LABEL: Record<RoofMaterial, string> = {
  RCC: "RCC",
  CONCRETE: "Concrete",
  METAL: "Metal",
  TILE: "Tile",
  SHEET: "Sheet",
  OTHER: "Other",
};
const ROOF_SLOPE_LABEL: Record<RoofSlope, string> = { FLAT: "Flat", LOW: "Low slope", MEDIUM: "Medium slope", HIGH: "High slope" };

export async function generateMetadata({ params }: { params: Promise<{ jobId: string }> }): Promise<Metadata> {
  const { jobId } = await params;
  const job = await getVendorJob(jobId).catch(() => null);
  if (!job) return { title: "Job not found" };
  return {
    title: `${job.siteName} — job`,
    description: `Vendor job at ${job.siteName}, ${job.district}, ${job.state}: deadline, payout, and capture requirements.`,
  };
}

export default async function VendorJobDetailPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const job = await orRedirectToLogin(getVendorJob(jobId));
  if (!job) notFound();
  const site = await getSite(job.siteId).catch(() => null);

  return (
    <div className="space-y-6">
      <PageHeader
        title={job.siteName}
        description={`${siteTypeLabel(job.siteType)} · ${job.district}, ${job.state}`}
        actions={<SlaBadge status={job.status} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.1fr_1fr]">
        <div className="space-y-6">
          <Card className="p-5 space-y-3">
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <MapPin size={15} strokeWidth={1.75} aria-hidden="true" />
              {site?.address ?? `${job.district}, ${job.state}`}
            </div>
            <div className="flex items-center gap-2 text-sm text-ink-soft">
              <CalendarClock size={15} strokeWidth={1.75} aria-hidden="true" />
              Deadline: {formatDate(job.deadline)}
            </div>
          </Card>

          <section aria-labelledby="requirements-heading">
            <h2 id="requirements-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              <ListChecks size={14} strokeWidth={1.75} aria-hidden="true" />
              Requirements
            </h2>
            <Card className="p-4">
              <ul className="space-y-2 text-sm text-ink">
                {job.requirements.map((req) => (
                  <li key={req} className="flex items-start gap-2">
                    <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" aria-hidden="true" />
                    {req}
                  </li>
                ))}
              </ul>
            </Card>
          </section>

          {site && (site.roofType || site.roofMaterial || site.roofSlope || site.roofConstructionYear) && (
            <section aria-labelledby="roof-info-heading">
              <h2 id="roof-info-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
                <Home size={14} strokeWidth={1.75} aria-hidden="true" />
                Roof information <span className="normal-case text-ink-faint">(customer-reported)</span>
              </h2>
              <Card className="grid grid-cols-2 gap-3 p-4 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-xs text-ink-faint">Roof type</p>
                  <p className="text-ink">{site.roofType ? ROOF_TYPE_LABEL[site.roofType] : "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Material</p>
                  <p className="text-ink">{site.roofMaterial ? ROOF_MATERIAL_LABEL[site.roofMaterial] : "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Slope</p>
                  <p className="text-ink">{site.roofSlope ? ROOF_SLOPE_LABEL[site.roofSlope] : "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Construction year</p>
                  <p className="font-mono tabular text-ink">{site.roofConstructionYear ?? "—"}</p>
                </div>
              </Card>
            </section>
          )}

          {site && (site.electricityBoard || site.consumerNumber || site.connectionType || site.sanctionedLoadKw || site.monthlyConsumptionKwh.length > 0) && (
            <section aria-labelledby="electricity-info-heading">
              <h2 id="electricity-info-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
                <Zap size={14} strokeWidth={1.75} aria-hidden="true" />
                Electricity connection <span className="normal-case text-ink-faint">(customer-reported)</span>
              </h2>
              <Card className="p-4 text-sm space-y-3">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <p className="text-xs text-ink-faint">Board</p>
                    <p className="text-ink">{site.electricityBoard ?? "—"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">Consumer no.</p>
                    <p className="font-mono tabular text-ink">{site.consumerNumber ?? "—"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">Connection</p>
                    <p className="text-ink">{site.connectionType ? CONNECTION_TYPE_LABEL[site.connectionType] : "—"}</p>
                  </div>
                  <div>
                    <p className="text-xs text-ink-faint">Sanctioned load</p>
                    <p className="font-mono tabular text-ink">{site.sanctionedLoadKw != null ? `${site.sanctionedLoadKw} kW` : "—"}</p>
                  </div>
                </div>
                {site.monthlyConsumptionKwh.length > 0 && (
                  <div>
                    <p className="mb-1 text-xs text-ink-faint">
                      Consumption — avg{" "}
                      {Math.round(
                        site.monthlyConsumptionKwh.reduce((sum, e) => sum + e.unitsKwh, 0) / site.monthlyConsumptionKwh.length
                      )}{" "}
                      kWh/mo · annual {Math.round(site.monthlyConsumptionKwh.reduce((sum, e) => sum + e.unitsKwh, 0))} kWh
                    </p>
                    <div className="flex flex-wrap gap-2 font-mono tabular text-xs text-ink-soft">
                      {site.monthlyConsumptionKwh.map((e) => (
                        <span key={e.month} className="rounded bg-surface-2 px-1.5 py-0.5">
                          {e.month}: {e.unitsKwh}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            </section>
          )}

          {site && (site.batteryRequired || site.backupRequired) && (
            <section aria-labelledby="battery-interest-heading">
              <h2 id="battery-interest-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-ink-faint">
                <BatteryCharging size={14} strokeWidth={1.75} aria-hidden="true" />
                Battery / backup interest <span className="normal-case text-ink-faint">(customer-reported)</span>
              </h2>
              <Card className="grid grid-cols-2 gap-3 p-4 text-sm sm:grid-cols-4">
                <div>
                  <p className="text-xs text-ink-faint">Battery interest</p>
                  <p className="text-ink">{site.batteryRequired ? "Yes" : "No"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Backup needed</p>
                  <p className="text-ink">{site.backupRequired ? "Yes" : "No"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Required backup</p>
                  <p className="font-mono tabular text-ink">{site.requiredBackupHours != null ? `${site.requiredBackupHours} h` : "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-faint">Critical loads</p>
                  <p className="text-ink">{site.criticalLoads ?? "—"}</p>
                </div>
              </Card>
            </section>
          )}

          <ObstacleSurveySection job={job} />
          <StructuralAssessmentSection job={job} />
          <ElectricalAssessmentSection job={job} />
          <InstallationConstraintsSection job={job} />
          <SafetyAssessmentSection job={job} />
          <BatteryAssessmentSection job={job} />
        </div>

        <div className="space-y-6">
          <section aria-labelledby="actions-heading">
            <h2 id="actions-heading" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-faint">
              Actions
            </h2>
            <JobActions job={job} />
          </section>
        </div>
      </div>
    </div>
  );
}
