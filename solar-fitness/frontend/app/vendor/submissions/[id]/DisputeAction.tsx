"use client";

import { useState } from "react";
import { AlertTriangle, Send } from "lucide-react";
import { Button, Card } from "@/components/ui/Primitives";
import { useDisputeSubmission } from "@/lib/query/hooks";
import type { VendorJob } from "@/lib/types";

export function DisputeAction({ job }: { job: VendorJob }) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const dispute = useDisputeSubmission(job.id);

  if (job.disputeStatus === "open") {
    return (
      <Card className="flex items-start gap-3 p-4" style={{ borderColor: "var(--warn)", background: "var(--warn-bg)" }}>
        <AlertTriangle size={18} strokeWidth={1.75} className="mt-0.5" style={{ color: "var(--warn)" }} aria-hidden="true" />
        <div>
          <p className="font-medium text-ink">Dispute open</p>
          <p className="mt-1 text-sm text-ink-soft">{job.disputeReason}</p>
        </div>
      </Card>
    );
  }

  if (job.disputeStatus === "resolved") {
    return (
      <Card className="p-4">
        <p className="font-medium text-ink">Dispute resolved</p>
        <p className="mt-1 text-sm text-ink-soft">{job.disputeReason}</p>
      </Card>
    );
  }

  if (!open) {
    return (
      <Button variant="danger" onClick={() => setOpen(true)}>
        <AlertTriangle size={15} strokeWidth={1.75} /> Dispute this payout
      </Button>
    );
  }

  return (
    <Card className="space-y-3 p-4">
      <label htmlFor="dispute-reason" className="block text-sm font-medium text-ink">
        Reason for dispute
      </label>
      <textarea
        id="dispute-reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={3}
        placeholder="Explain why the reconciled payout or measured capacity looks wrong…"
        className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-teal"
      />
      <div className="flex gap-2">
        <Button
          onClick={async () => {
            await dispute.mutateAsync(reason || "No reason provided.");
            setOpen(false);
          }}
          disabled={!reason.trim() || dispute.isPending}
        >
          <Send size={15} strokeWidth={1.75} /> {dispute.isPending ? "Submitting…" : "Submit dispute"}
        </Button>
        <Button variant="secondary" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </Card>
  );
}
