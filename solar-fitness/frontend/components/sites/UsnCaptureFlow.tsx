"use client";

import { useRef, useState } from "react";
import { CheckCircle2, Camera, FileText, Keyboard, ShieldCheck } from "lucide-react";
import { Button, Card, Badge } from "@/components/ui/Primitives";
import { useCaptureManualUsn, useConfirmUsn, useExtractUsn } from "@/lib/query/hooks";
import type { Site } from "@/lib/types";
import { cn } from "@/lib/utils";

type Method = "manual" | "bill" | "payment_proof";

export function UsnCaptureFlow({ site, mobile = false }: { site: Site; mobile?: boolean }) {
  const [method, setMethod] = useState<Method>("manual");
  const [manualValue, setManualValue] = useState(site.usn ?? "");
  const [editableValue, setEditableValue] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const captureManual = useCaptureManualUsn(site.id);
  const extract = useExtractUsn(site.id);
  const confirm = useConfirmUsn(site.id);

  function pickFile(kind: "bill" | "payment_proof") {
    setMethod(kind);
    fileInputRef.current?.click();
  }

  async function onFileSelected(kind: "bill" | "payment_proof", file: File) {
    const preview = await extract.mutateAsync({ kind, file });
    setEditableValue(preview.usn ?? "");
  }

  const valueToConfirm = method === "manual" ? manualValue : editableValue;
  const confirming = captureManual.isPending || confirm.isPending;
  const finalUsn = captureManual.data?.usn ?? confirm.data?.usn ?? site.usn;

  async function handleConfirm() {
    if (!valueToConfirm) return;
    if (method === "manual") {
      await captureManual.mutateAsync(valueToConfirm);
    } else if (extract.data) {
      await confirm.mutateAsync({ uploadId: extract.data.uploadId, confirmedUsn: valueToConfirm });
    } else {
      return;
    }
    setConfirmed(true);
  }

  if (confirmed || site.usnStatus === "confirmed") {
    return (
      <Card className="flex items-start gap-3 p-4">
        <ShieldCheck size={20} strokeWidth={1.75} className="mt-0.5 text-blue" aria-hidden="true" />
        <div>
          <p className="font-medium text-ink">USN confirmed</p>
          <p className="mt-1 font-mono tabular text-sm text-ink-soft">{finalUsn}</p>
        </div>
      </Card>
    );
  }

  return (
    <div className={cn("space-y-4", mobile && "max-w-md")}>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) void onFileSelected(method === "payment_proof" ? "payment_proof" : "bill", file);
        }}
      />
      <div className={cn("grid gap-2", mobile ? "grid-cols-1" : "grid-cols-3")}>
        <MethodButton icon={Keyboard} label="Manual entry" active={method === "manual"} onClick={() => setMethod("manual")} mobile={mobile} />
        <MethodButton icon={FileText} label="Electricity bill OCR" active={method === "bill"} onClick={() => pickFile("bill")} mobile={mobile} />
        <MethodButton icon={Camera} label="Payment proof OCR" active={method === "payment_proof"} onClick={() => pickFile("payment_proof")} mobile={mobile} />
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
        ) : extract.isPending ? (
          <p className="text-sm text-ink-soft">Running OCR extraction…</p>
        ) : extract.data ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-ink-faint">
              Extracted from {method === "bill" ? "electricity bill" : "payment proof"}
            </p>
            <Badge tone={extract.data.extractionStatus === "extracted" ? "blue" : "amber"} className="mt-2">
              {extract.data.extractionStatus === "extracted"
                ? "USN found"
                : extract.data.extractionStatus === "not_found"
                  ? "No USN detected — enter or correct below"
                  : "Extraction failed — enter or correct below"}
            </Badge>
            <label htmlFor="usn-extracted" className="mt-3 mb-1 block text-sm font-medium text-ink">
              USN
            </label>
            <input
              id="usn-extracted"
              value={editableValue}
              onChange={(e) => setEditableValue(e.target.value)}
              placeholder="USN123456789"
              className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-3 font-mono tabular text-base text-ink outline-none focus:border-blue"
            />
            <p className="mt-3 text-sm text-ink-soft">Confirm this value before it is stored against the site record.</p>
          </div>
        ) : (
          <p className="text-sm text-ink-soft">Upload a scan to extract the USN automatically.</p>
        )}
      </Card>

      <Button onClick={handleConfirm} disabled={!valueToConfirm || confirming} className={cn(mobile && "w-full")}>
        <CheckCircle2 size={15} strokeWidth={1.75} /> {confirming ? "Confirming…" : "Confirm & store USN"}
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
