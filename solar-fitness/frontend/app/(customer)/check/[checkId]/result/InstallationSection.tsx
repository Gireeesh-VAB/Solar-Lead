"use client";

// The customer's end of the post-approval pipeline, in one card that
// changes shape three times:
//
//   1. approved + a quotation to accept  -> the "Accept quotation" CTA,
//      the missing trigger that opens an installation project at all;
//   2. project underway                  -> a compact stage strip;
//   3. installer has submitted commissioning -> the final sign-off.
//
// Null-safe like every other card on this page: a 404 from
// GET /app/checks/{id}/installation is the normal "no project yet"
// state, not an error, so the whole card renders nothing rather than an
// error box when there is nothing to say.

import { useState } from "react";
import { CheckCircle2, HardHat } from "lucide-react";
import {
  useAcceptInstallation,
  useAcceptQuotation,
  useCheckInstallation,
  useSubmitVendorReview,
} from "@/lib/query/hooks";
import { Badge, Button, Card } from "@/components/ui/Primitives";
import { StageProgress, stageLabel } from "@/components/installations/StageProgress";
import { StarRating } from "@/components/ui/StarRating";
import { ApiError } from "@/lib/api/fetchClient";
import type { FinancialEstimate } from "@/lib/types";
import { formatInr } from "@/lib/utils";

export function InstallationSection({
  checkId,
  reviewStatus,
  financialEstimate,
}: {
  checkId: string;
  reviewStatus?: string;
  financialEstimate?: FinancialEstimate;
}) {
  // Only an approved enquiry can ever have a quotation or a project.
  const approved = reviewStatus === "approved";
  const installation = useCheckInstallation(checkId, approved);
  const acceptQuotation = useAcceptQuotation(checkId);
  const acceptInstallation = useAcceptInstallation(checkId);

  if (!approved) return null;
  if (installation.isLoading) return null;

  const project = installation.data;
  const notFound =
    installation.isError && installation.error instanceof ApiError && installation.error.status === 404;

  // Nothing yet: offer the acceptance, but only once there is a real
  // costed quotation to accept — a bare approval isn't one.
  if (!project) {
    if (!notFound || !financialEstimate) return null;
    const total = financialEstimate.customerContributionInr ?? financialEstimate.totalProjectCostInr;
    return (
      <Card className="space-y-3 p-4">
        <Header title="Ready to install" />
        <p className="text-sm text-ink-soft">
          Your enquiry is approved and an installer is assigned.
          {total != null && (
            <> Accepting the quotation of {formatInr(total)} starts the installation.</>
          )}
        </p>
        <Button
          className="w-full"
          disabled={acceptQuotation.isPending}
          onClick={() => acceptQuotation.mutate()}
        >
          {acceptQuotation.isPending ? "Accepting…" : "Accept quotation"}
        </Button>
        {acceptQuotation.isError && (
          <p className="text-xs text-ink-faint">
            Could not accept the quotation just now. Please try again.
          </p>
        )}
      </Card>
    );
  }

  const done = project.status === "completed";
  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center justify-between gap-2">
        <Header title="Your installation" />
        <Badge tone={done ? "blue" : "green"}>{stageLabel(project.status)}</Badge>
      </div>

      <StageProgress stages={project.stages} stageIndex={project.stageIndex} compact />

      <dl className="grid grid-cols-2 gap-2">
        <Stat
          label="System size"
          value={`${project.approvedCapacityKwp.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWp`}
        />
        <Stat label="Quality check" value={project.qcApproved ? "Approved" : "In progress"} />
      </dl>

      {project.commissioningSubmitted && !project.customerAccepted && (
        <div className="space-y-2 border-t border-line pt-3">
          <p className="text-sm text-ink-soft">
            Your installer has finished and submitted the commissioning details. Confirm you&apos;re
            happy with the installation to complete the handover.
          </p>
          <Button
            className="w-full"
            disabled={acceptInstallation.isPending}
            onClick={() => acceptInstallation.mutate()}
          >
            <CheckCircle2 size={15} strokeWidth={1.75} />
            {acceptInstallation.isPending ? "Confirming…" : "Accept installation"}
          </Button>
        </div>
      )}

      {project.customerAccepted && !project.adminApproved && (
        <p className="border-t border-line pt-3 text-xs text-ink-faint">
          Thanks — your acceptance is recorded. Final approval is with our team.
        </p>
      )}
      {project.adminApproved && (
        <p className="border-t border-line pt-3 text-xs text-ink-faint">
          Commissioning approved. Your system is live.
        </p>
      )}

      {project.customerAccepted && (project.reviewed ? (
        <p className="flex items-center gap-1.5 border-t border-line pt-3 text-xs text-ink-faint">
          <CheckCircle2 size={13} strokeWidth={1.75} className="text-good" aria-hidden="true" />
          Thanks for reviewing your vendor.
        </p>
      ) : (
        <VendorReviewForm checkId={checkId} />
      ))}
    </Card>
  );
}

function VendorReviewForm({ checkId }: { checkId: string }) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const submitReview = useSubmitVendorReview(checkId);

  if (submitReview.isSuccess) {
    return (
      <p className="flex items-center gap-1.5 border-t border-line pt-3 text-xs text-ink-faint">
        <CheckCircle2 size={13} strokeWidth={1.75} className="text-good" aria-hidden="true" />
        Thanks for reviewing your vendor.
      </p>
    );
  }

  return (
    <div className="space-y-2 border-t border-line pt-3">
      <p className="text-sm font-medium text-ink">Rate your vendor</p>
      <StarRating value={rating} onChange={setRating} size={20} />
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value)}
        placeholder="Optional — how was the installation?"
        rows={2}
        maxLength={2000}
        className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-2 py-1.5 text-sm text-ink"
      />
      {submitReview.isError && (
        <p className="text-xs text-bad">Could not submit your review just now. Please try again.</p>
      )}
      <Button
        className="w-full"
        disabled={rating === 0 || submitReview.isPending}
        onClick={() => submitReview.mutate({ rating, comment: comment.trim() || undefined })}
      >
        {submitReview.isPending ? "Submitting…" : "Submit review"}
      </Button>
    </div>
  );
}

function Header({ title }: { title: string }) {
  return (
    <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-teal"
        style={{ background: "var(--teal-soft, rgba(20,148,132,0.12))" }}
        aria-hidden="true"
      >
        <HardHat size={15} strokeWidth={1.75} />
      </span>
      {title}
    </h2>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-app)] bg-surface-2 px-3 py-2">
      <dt className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-ink">{value}</dd>
    </div>
  );
}
