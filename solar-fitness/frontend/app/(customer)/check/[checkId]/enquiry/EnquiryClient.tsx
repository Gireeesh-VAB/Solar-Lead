"use client";

// Vendor selection is optional — see repositories/assessments.py::
// raise_enquiry()'s own docstring: submitting without a vendor is a
// completely valid, first-class path ("Unassigned"), not a fallback.
// Nearby/available vendors come from real district/state matching
// (engine/vendors.py::best_available_vendor_for_district's underlying
// data) — no fabricated distance, no contact info before a vendor has
// actually agreed to the job.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, Briefcase, CheckCircle2, Gauge, Loader2, MapPin, Send, ShieldCheck } from "lucide-react";
import { Button, Card, ErrorState } from "@/components/ui/Primitives";
import { StarRating } from "@/components/ui/StarRating";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { useNearbyVendors, useRaiseEnquiry } from "@/lib/query/hooks";
import type { NearbyVendor } from "@/lib/api/client";
import type { Verdict } from "@/lib/types";
import { cn, formatKwp } from "@/lib/utils";

const MATCH_LABEL: Record<NearbyVendor["matchCategory"], string> = {
  same_district: "Serves your district",
  same_state: "Serves your state",
  other: "Available",
};

const fadeUp = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.07, delayChildren: 0.05 },
  },
};

export function EnquiryClient({
  checkId,
  checkName,
  verdict,
  capacityKwp,
}: {
  checkId: string;
  checkName: string;
  verdict: Verdict;
  capacityKwp: number;
}) {
  const [selectedVendorId, setSelectedVendorId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const { data: vendors, isLoading, isError } = useNearbyVendors(checkId);
  const raiseEnquiry = useRaiseEnquiry(checkId);
  const router = useRouter();

  const selectedVendor = vendors?.find((v) => v.id === selectedVendorId);

  const submit = (vendorId?: string) => {
    raiseEnquiry.mutate(
      { vendorId },
      {
        onSuccess: () => {
          setSubmitted(true);
          // A brief, visible confirmation before handing off to the result
          // page — an instant redirect gave no acknowledgement the request
          // actually went through. Router prefetch means the next page is
          // already warm by the time this fires.
          setTimeout(() => router.push(`/check/${checkId}/result`), 1800);
        },
      }
    );
  };

  if (submitted) {
    return (
      <AnimatePresence mode="wait">
        <motion.div
          key="confirmation"
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.35, ease: "easeOut" }}
          className="mx-auto flex max-w-xl flex-col items-center gap-4 py-20 text-center"
        >
          <motion.span
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 18, delay: 0.1 }}
            className="flex h-16 w-16 items-center justify-center rounded-full bg-good-bg text-good"
          >
            <CheckCircle2 size={32} strokeWidth={1.75} />
          </motion.span>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.3 }}
          >
            <p className="text-lg font-semibold text-ink">Request submitted</p>
            <p className="mt-1 max-w-xs text-sm leading-relaxed text-ink-soft">
              {selectedVendor
                ? `We've sent your request to ${selectedVendor.name} — pending Super Admin review.`
                : "Our admin team will review your enquiry and assign a vendor for you."}
            </p>
          </motion.div>
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.3 }}
            className="flex items-center gap-1.5 text-xs text-ink-faint"
          >
            <Loader2 size={13} className="animate-spin" aria-hidden="true" />
            Taking you to your check…
          </motion.p>
        </motion.div>
      </AnimatePresence>
    );
  }

  return (
    <motion.div
      initial="hidden"
      animate="show"
      exit={{ opacity: 0, y: -8 }}
      variants={stagger}
      className="mx-auto flex max-w-xl flex-col gap-6"
    >
      {/* ---------- Header ---------- */}
      <motion.div variants={fadeUp} className="text-center">
        <p className="truncate text-xs font-medium uppercase tracking-wide text-ink-faint">{checkName}</p>
        <div className="mt-2 flex justify-center">
          <VerdictChip verdict={verdict} size="lg" />
        </div>
      </motion.div>

      {/* ---------- Recommended system ---------- */}
      <motion.div variants={fadeUp}>
        <Card className="relative overflow-hidden p-5 text-center">
          <div
            aria-hidden="true"
            className="absolute inset-x-0 top-0 h-0.5"
            style={{ background: "linear-gradient(90deg, var(--amber), transparent)" }}
          />
          <span
            className="mx-auto flex h-12 w-12 items-center justify-center rounded-full border"
            style={{
              background: "linear-gradient(150deg, var(--warn-bg), var(--surface-2))",
              color: "var(--amber)",
              borderColor: "color-mix(in srgb, var(--amber) 25%, transparent)",
              boxShadow: "var(--shadow-float)",
            }}
            aria-hidden="true"
          >
            <Gauge size={22} strokeWidth={1.75} />
          </span>
          <p className="mt-3 text-xs font-medium uppercase tracking-wide text-ink-faint">Recommended system</p>
          <p className="mt-1 text-2xl font-semibold text-ink">
            {capacityKwp > 0 ? formatKwp(capacityKwp) : "—"}
          </p>
        </Card>
      </motion.div>

      {/* ---------- Enquiry ---------- */}
      <motion.div variants={fadeUp}>
        <p className="mb-1.5 text-base font-semibold text-ink">Raise an enquiry</p>
        <p className="mb-4 text-sm leading-relaxed text-ink-soft">
          Pick a vendor to work with, or submit without one and our admin team will assign one for you.
        </p>

        <div className="space-y-4">
          {isLoading && (
            <p className="flex items-center gap-1.5 text-sm text-ink-soft">
              <Loader2 size={14} className="animate-spin" aria-hidden="true" />
              Finding vendors near you…
            </p>
          )}

          {isError && <ErrorState description="Couldn't load nearby vendors. You can still submit without one." />}

          {vendors && vendors.length === 0 && (
            <p className="rounded-[var(--radius-app)] border border-dashed border-line px-4 py-3 text-sm text-ink-soft">
              No vendors are available in your area yet — submit your enquiry and our admin team will assign one.
            </p>
          )}

          {vendors && vendors.length > 0 && (
            <motion.ul variants={stagger} initial="hidden" animate="show" className="space-y-2.5">
              {vendors.map((vendor) => {
                const selected = selectedVendorId === vendor.id;
                return (
                  <motion.li key={vendor.id} variants={fadeUp}>
                    <button
                      type="button"
                      onClick={() => setSelectedVendorId(selected ? null : vendor.id)}
                      aria-pressed={selected}
                      className={cn(
                        "flex min-h-[44px] w-full items-start justify-between gap-3 rounded-[var(--radius-app)] border p-4 text-left transition-all duration-200",
                        selected
                          ? "border-blue bg-[var(--surface-2)] shadow-[var(--shadow-float)]"
                          : "border-line hover:-translate-y-0.5 hover:border-blue hover:shadow-[var(--shadow-float)]"
                      )}
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-ink">{vendor.name}</span>
                          {selected && <BadgeCheck size={15} className="shrink-0 text-blue" aria-hidden="true" />}
                        </div>
                        <p className="mt-1 flex items-center gap-1 text-xs text-ink-soft">
                          <MapPin size={11} strokeWidth={1.75} aria-hidden="true" />
                          {MATCH_LABEL[vendor.matchCategory]}
                          {vendor.region && ` · ${vendor.region}`}
                        </p>
                        {vendor.certifications.length > 0 && (
                          <p className="mt-1 truncate text-xs text-ink-faint">{vendor.certifications.join(", ")}</p>
                        )}
                      </div>
                      <div className="shrink-0 text-right">
                        {vendor.reviewCount > 0 ? (
                          <div className="flex items-center justify-end gap-1">
                            <StarRating value={vendor.averageRating ?? 0} size={12} />
                            <span className="text-xs font-medium text-ink-soft">
                              {vendor.averageRating?.toFixed(1)}
                            </span>
                            <span className="text-xs text-ink-faint">({vendor.reviewCount})</span>
                          </div>
                        ) : (
                          <span className="text-xs text-ink-faint">No reviews yet</span>
                        )}
                        <p className="mt-1 flex items-center justify-end gap-1 text-xs text-ink-faint">
                          <Briefcase size={11} strokeWidth={1.75} aria-hidden="true" />
                          {vendor.jobsCompleted} completed
                          {vendor.activeJobs > 0 && ` · ${vendor.activeJobs} in progress`}
                        </p>
                      </div>
                    </button>
                  </motion.li>
                );
              })}
            </motion.ul>
          )}

          {raiseEnquiry.isError && (
            <p className="text-sm" style={{ color: "var(--bad)" }} role="alert">
              Something went wrong submitting your enquiry. Please try again.
            </p>
          )}

          <div className="flex flex-col gap-2.5 pt-1 sm:flex-row">
            <Button
              className="min-h-[44px] flex-1 py-3 text-sm font-semibold text-white transition-all duration-200 hover:-translate-y-0.5 disabled:hover:translate-y-0"
              style={{
                background: "linear-gradient(135deg, var(--brand), var(--brand-soft))",
                boxShadow: "var(--shadow-float)",
              }}
              disabled={!selectedVendorId || raiseEnquiry.isPending}
              onClick={() => submit(selectedVendorId ?? undefined)}
            >
              {raiseEnquiry.isPending && selectedVendorId && (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              )}
              {!raiseEnquiry.isPending && <Send size={15} strokeWidth={2} aria-hidden="true" />}
              {raiseEnquiry.isPending && selectedVendorId
                ? "Submitting…"
                : selectedVendorId
                  ? "Submit with selected vendor"
                  : "Select a vendor above, or submit without one"}
            </Button>
            <Button
              variant="secondary"
              className="min-h-[44px] flex-1 py-3 text-sm font-medium"
              disabled={raiseEnquiry.isPending}
              onClick={() => submit(undefined)}
            >
              {raiseEnquiry.isPending && !selectedVendorId && (
                <Loader2 size={15} className="animate-spin" aria-hidden="true" />
              )}
              {raiseEnquiry.isPending && !selectedVendorId ? "Submitting…" : "Submit without selecting a vendor"}
            </Button>
          </div>

          <p className="flex items-center justify-center gap-1.5 pt-1 text-xs text-ink-faint">
            <ShieldCheck size={13} strokeWidth={1.75} aria-hidden="true" />
            Free · No commitment until a vendor confirms
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}
