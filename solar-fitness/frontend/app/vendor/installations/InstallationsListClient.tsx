"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { HardHat, Zap } from "lucide-react";
import { useVendorInstallations } from "@/lib/query/hooks";
import { Card, CardSkeleton, EmptyState, ErrorState, Badge } from "@/components/ui/Primitives";
import { Select } from "@/components/ui/Select";
import { StageProgress, stageLabel } from "@/components/installations/StageProgress";
import { INSTALLATION_STAGES, type InstallationProject } from "@/lib/types";
import { formatDate } from "@/lib/utils";

const fadeUp = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0 } };
const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } } };

export function InstallationsListClient() {
  const [status, setStatus] = useState("");
  const projects = useVendorInstallations({ status: status || undefined });

  return (
    <div className="space-y-4">
      <Select
        value={status}
        onChange={(e) => setStatus(e.target.value)}
        aria-label="Filter by stage"
      >
        <option value="">All stages</option>
        {INSTALLATION_STAGES.map((s) => (
          <option key={s} value={s}>
            {stageLabel(s)}
          </option>
        ))}
      </Select>

      {projects.isLoading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      )}
      {projects.isError && (
        <ErrorState
          description="Could not load your installation projects."
          onRetry={() => projects.refetch()}
        />
      )}
      {projects.data && projects.data.length === 0 && (
        <EmptyState
          icon={<HardHat size={28} strokeWidth={1.5} />}
          title="No installation projects yet"
          description="A project appears here once a customer accepts the quotation on a job you were assigned."
        />
      )}
      {projects.data && projects.data.length > 0 && (
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        >
          {projects.data.map((project) => (
            <motion.div key={project.id} variants={fadeUp}>
              <ProjectCard project={project} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}

function ProjectCard({ project }: { project: InstallationProject }) {
  return (
    <Card interactive className="flex h-full flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[var(--good-bg)] text-brand"
            aria-hidden="true"
          >
            <Zap size={16} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <Link
              href={`/vendor/installations/${project.id}`}
              className="block truncate font-medium text-ink hover:text-brand"
            >
              {project.approvedCapacityKwp.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWp
              installation
            </Link>
            <p className="mt-0.5 truncate text-xs text-ink-soft">
              Opened {formatDate(project.createdAt)}
            </p>
          </div>
        </div>
        <Badge tone={project.status === "completed" ? "blue" : "neutral"}>
          {stageLabel(project.status)}
        </Badge>
      </div>

      <StageProgress stages={project.stages} stageIndex={project.stageIndex} compact />

      <div className="mt-auto flex items-center justify-end border-t border-line pt-3">
        <Link
          href={`/vendor/installations/${project.id}`}
          className="text-sm text-brand hover:underline"
        >
          Open project
        </Link>
      </div>
    </Card>
  );
}
