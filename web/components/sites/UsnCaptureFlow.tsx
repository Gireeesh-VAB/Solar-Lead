"use client";

import { useState } from "react";
import { CheckCircle2, Camera, FileText, Keyboard, ShieldCheck } from "lucide-react";
import { Button, Card, Badge } from "@/components/ui/Primitives";
import { useOcrExtraction, useSubmitUsn } from "@/lib/query/hooks";
import type { Site } from "@/lib/types";
import { cn } from "@/lib/utils";

type Method = "manual" | "bill" | "payment_proof";

export function UsnCaptureFlow({ site, mobile = false }: { site: Site; mobile?: boolean }) {
  const [method, setMethod] = useState<Method>("manual");
  const [manualValue, setManualValue] = useState(site.usn ?? "");
  const [extracted, setExtracted] = useState<{ extractedUsn: string; confidence: number; sourceLabel: string } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const ocr = useOcrExtraction();
  const submit = useSubmitUsn(site.id);

  async function runOcr(kind: "bill" | "payment_proof") {
    setMethod(kind);
    setExtracted(null);
    setConfirmed(false);
    const result = await ocr.mutateAsync(kind);
    setExtracted(result);
  }

  const valueToConfirm = method === "manual" ? manualValue : extracted?.extractedUsn ?? "";

  async function handleConfirm() {
    if (!valueToConfirm) return;
    await submit.mutateAsync({ usn: valueToConfirm, method: method === "manual" ? "manual" : `${method}_ocr` as const });
    setConfirmed(true);
  }

  if (submit.isSuccess || confirmed || site.usnStatus === "confirmed") {
    return (
      <Card className="flex items-start gap-3 p-4">
        <ShieldCheck size={20} strokeWidth={1.75} className="mt-0.5 text-blue" aria-hidden="true" />
        <div>
          <p className="font-medium text-ink">USN confirmed</p>
          <p className="mt-1 font-mono tabular text-sm text-ink-soft">{submit.data?.usn ?? site.usn}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className={cn("space-y-4", mobile && "max-w-md")}>
      <div className={cn("grid gap-2", mobile ? "grid-cols-1" : "grid-cols-3")}>
        <MethodButton icon={Keyboard} label="Manual entry" active={method === "manual"} onClick={() => setMethod("manual")} mobile={mobile} />
        <MethodButton icon={FileText} label="Electricity bill OCR" active={method === "bill"} onClick={() => runOcr("bill")} mobile={mobile} />
        <MethodButton icon={Camera} label="Payment proof OCR" active={method === "payment_proof"} onClick={() => runOcr("payment_proof")} mobile={mobile} />
      </div>

      <Card className="p-4">
        {method === "manual" ? (
          <div>
            <label htmlFor="usn-manual" className="mb-1 block text-sm font-medium text-ink">
              Unique Service Number (USN)
            </label>
            <input
              id="usn-manual"
              value={manualValue}
              onChange={(e) => setManualValue(e.target.value)}
              placeholder="USN123456789"
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-3 font-mono tabular text-base text-ink outline-none focus:border-blue"
            />
          </div>
        ) : ocr.isPending ? (
          <p className="text-sm text-ink-soft">Running OCR extraction…</p>
        ) : extracted ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">Extracted from {extracted.sourceLabel}</p>
            <p className="mt-1 font-mono tabular text-lg text-ink">{extracted.extractedUsn}</p>
            <Badge tone={extracted.confidence > 0.85 ? "blue" : "amber"} className="mt-2">
              OCR confidence {Math.round(extracted.confidence * 100)}%
            </Badge>
            <p className="mt-3 text-sm text-ink-soft">Confirm this value before it is stored against the site record.</p>
          </div>
        ) : (
          <p className="text-sm text-ink-soft">Upload a scan to extract the USN automatically.</p>
        )}
      </Card>

      <Button onClick={handleConfirm} disabled={!valueToConfirm || submit.isPending} className={cn(mobile && "w-full")}>
        <CheckCircle2 size={15} strokeWidth={1.75} /> {submit.isPending ? "Confirming…" : "Confirm & store USN"}
      </Button>
    </div>
  );
}

function MethodButton({
  icon: Icon,
  label,
  active,
  onClick,
  mobile,
}: {
  icon: typeof Keyboard;
  label: string;
  active: boolean;
  onClick: () => void;
  mobile?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-2 rounded-[var(--radius-app)] border p-3 text-sm",
        mobile && "min-h-[52px]",
        active ? "border-amber bg-[var(--warn-bg)] text-ink" : "border-line text-ink-soft hover:border-blue"
      )}
    >
      <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
      {label}
    </button>
  );
}
