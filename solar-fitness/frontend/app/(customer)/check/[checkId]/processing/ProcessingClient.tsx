"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { ErrorState } from "@/components/ui/Primitives";
import { useCompleteCheck, useCheckAssessmentStatus } from "@/lib/query/hooks";
import type { AssessmentStage } from "@/lib/api/client";
import { StageAnimation, VIDEO_STAGE_RANGES } from "./StageAnimation";

// Mirrors routers/assessments.py::ASSESSMENT_STAGES exactly — order and
// keys must match, since this list's position is what drives "done" vs
// "current" vs "not yet" below. The backend reports which real stage of
// the pipeline is running; this app owns the words shown for each, same
// "backend emits symbolic keys, frontend renders copy" split every other
// status/verdict enum in this app already uses.
const STAGES: { key: AssessmentStage; label: string }[] = [
  { key: "resolving_location", label: "Locating your site" },
  { key: "analyzing_roof_imagery", label: "Analyzing satellite imagery" },
  { key: "detecting_obstacles", label: "Detecting rooftop obstacles" },
  { key: "computing_usable_area", label: "Computing usable roof area" },
  { key: "sizing_system", label: "Sizing your recommended system" },
  { key: "placing_panels", label: "Placing solar panels on your roof" },
  { key: "scoring_feasibility", label: "Scoring feasibility" },
  { key: "finalizing_result", label: "Finalizing your result" },
];

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

// How long each step stays visible before the paced walk-through advances
// to the next one — matched to how long that stage's OWN video segment in
// StageAnimation actually plays (see VIDEO_STAGE_RANGES there), so the
// footage has time to play instead of being cut off mid-clip the moment
// the pacer moves on. finalizing_result has no video segment (the clip
// ends on the scoring gauges) — its SVG scene gets a fixed, comfortable
// dwell instead. A small floor keeps even the shortest real segment
// (scoring_feasibility, 0.5s of footage) readable rather than a flash.
const FINALIZING_DWELL_MS = 1800;
const MIN_DWELL_MS = 1800;

function dwellForStage(stage: AssessmentStage): number {
  const range = VIDEO_STAGE_RANGES[stage];
  if (!range) return FINALIZING_DWELL_MS;
  const [start, end] = range;
  return Math.max(MIN_DWELL_MS, Math.round((end - start) * 1000));
}

function stageIndex(stage: AssessmentStage | null | undefined): number {
  if (!stage) return 0;
  const i = STAGES.findIndex((s) => s.key === stage);
  return i === -1 ? 0 : i;
}

export function ProcessingClient({ checkId }: { checkId: string }) {
  const router = useRouter();
  const completeCheck = useCompleteCheck(checkId);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const jobStatusQuery = useCheckAssessmentStatus(checkId, jobId);
  const jobStatus = jobStatusQuery.data;

  // Starts a background assessment job (or restarts one, on retry) —
  // real backend work, not the fixed ~3s client-side animation this
  // screen used to fake regardless of how long the pipeline actually took.
  useEffect(() => {
    let cancelled = false;
    setJobId(null);
    completeCheck
      .mutateAsync()
      .then((job) => {
        if (!cancelled) setJobId(job.jobId);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Something went wrong.");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  // Reacts to the polled job's status once it stops being "pending"/"progress".
  // "ok" is handled separately below — it waits for the paced walk-through
  // to actually reach the last step first, rather than redirecting the
  // instant the backend says it's done.
  useEffect(() => {
    if (!jobStatus) return;
    if (jobStatus.status === "geometry_rejected") {
      // GEO-04: no automatic roof data at this location. Google covers
      // India building-by-building, so this is ordinary, not a fault —
      // written for the customer, same message the old synchronous 422
      // used to carry.
      setError(
        jobStatus.error ||
          "We couldn't find automatic roof data for this location. Draw the roof outline on the map to continue.",
      );
    } else if (jobStatus.status === "not_found" || jobStatus.status === "error") {
      setError(jobStatus.error || "Something went wrong.");
    }
  }, [jobStatus, checkId, router]);

  // How far the BACKEND actually is — before the first "progress" update
  // lands (job still "pending") the first stage is a reasonable default
  // since resolving_location genuinely runs first; "ok" maps to the last
  // stage index (see the pacing effect below for what happens next).
  const backendIndex =
    jobStatus?.status === "ok"
      ? STAGES.length - 1
      : jobStatus?.status === "progress"
        ? stageIndex(jobStatus.stage)
        : 0;

  const [displayedIndex, setDisplayedIndex] = useState(0);

  // A fast/cached run can finish several real stages between two 1200ms
  // polls, which used to make the step list jump straight from stage 1 to
  // stage 6 (or straight to "done"). This paces what's SHOWN to advance
  // one step at a time instead — it only ever walks toward backendIndex,
  // never ahead of it, so it's still grounded in real progress. All hooks
  // stay above the error early-return below (rules-of-hooks).
  useEffect(() => {
    if (displayedIndex >= backendIndex) return;
    const dwell = dwellForStage(STAGES[displayedIndex].key);
    const t = setTimeout(() => setDisplayedIndex((i) => Math.min(i + 1, backendIndex)), dwell);
    return () => clearTimeout(t);
  }, [displayedIndex, backendIndex]);

  // Resets the walk-through for a fresh job (a retry after an error).
  useEffect(() => {
    setDisplayedIndex(0);
  }, [jobId]);

  // Only leaves for the result page once the paced walk-through has
  // actually shown the last step for a moment — never an instant jump the
  // second the backend reports "ok".
  useEffect(() => {
    if (jobStatus?.status !== "ok" || displayedIndex < STAGES.length - 1) return;
    const t = setTimeout(() => router.replace(`/check/${checkId}/result`), dwellForStage(STAGES[displayedIndex].key));
    return () => clearTimeout(t);
  }, [jobStatus, displayedIndex, checkId, router]);

  if (error) {
    return (
      <div className="mx-auto max-w-sm py-16">
        <ErrorState
          title="We couldn't finish this check"
          description={error}
          onRetry={() => {
            setError(null);
            setJobId(null);
            setAttempt((a) => a + 1);
          }}
        />
      </div>
    );
  }

  const activeIndex = displayedIndex;
  const overallPercent = Math.round((activeIndex / (STAGES.length - 1)) * 100);

  const activeStage = STAGES[activeIndex]?.key ?? STAGES[0].key;

  return (
    <motion.div
      initial="hidden"
      animate="show"
      variants={stagger}
      className="mx-auto flex w-full max-w-sm flex-col gap-6 py-10 sm:py-14"
    >
      {/* ---------- Hero: stage scene + headline ---------- */}
      <motion.section
        variants={fadeUp}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="relative isolate overflow-hidden rounded-[var(--radius-app)] border border-line bg-surface px-5 py-8 text-center sm:px-8 sm:py-10"
      >
        {/* ambient backdrop */}
        <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
          <div
            className="absolute inset-0 opacity-[0.05]"
            style={{
              backgroundImage:
                "linear-gradient(to right, var(--ink) 1px, transparent 1px), linear-gradient(to bottom, var(--ink) 1px, transparent 1px)",
              backgroundSize: "28px 28px",
            }}
          />
          <motion.div
            animate={{ x: [0, 20, 0], y: [0, -14, 0] }}
            transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -top-16 left-1/2 h-56 w-[24rem] -translate-x-1/2 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--blue-soft), transparent 70%)", opacity: 0.35 }}
          />
          <motion.div
            animate={{ x: [0, -16, 0], y: [0, 12, 0] }}
            transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
            className="absolute -bottom-20 right-0 h-48 w-64 rounded-full blur-3xl"
            style={{ background: "radial-gradient(closest-side, var(--amber-soft), transparent 70%)", opacity: 0.3 }}
          />
        </div>

        <motion.span
          variants={fadeUp}
          className="mx-auto mb-5 inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-wide"
          style={{
            color: "var(--blue)",
            borderColor: "color-mix(in srgb, var(--blue) 30%, transparent)",
            background: "color-mix(in srgb, var(--blue) 8%, transparent)",
          }}
        >
          <Sparkles size={12} strokeWidth={2} aria-hidden="true" />
          Analyzing your roof
        </motion.span>

        <motion.div variants={fadeUp}>
          {/* AnimatePresence mode="wait" — the old scene fades fully out
              before the new one fades in, so a stage change reads as one
              smooth crossfade instead of an instant cut. */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeStage}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.35, ease: "easeInOut" }}
            >
              <StageAnimation stage={activeStage} />
            </motion.div>
          </AnimatePresence>
        </motion.div>

        <AnimatePresence mode="wait">
          <motion.h1
            key={activeIndex}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            className="mx-auto mt-6 max-w-[18rem] text-xl font-semibold leading-snug tracking-tight text-ink sm:text-2xl"
          >
            {STAGES[activeIndex]?.label ?? "Checking your location"}
          </motion.h1>
        </AnimatePresence>
        <motion.p variants={fadeUp} className="mx-auto mt-2 max-w-xs text-sm leading-relaxed text-ink-soft">
          This usually takes less than a minute.
        </motion.p>
      </motion.section>

      {/* Real overall progress, not a fixed-duration fake bar — width
          transitions smoothly between whatever stage the backend last
          reported, driven by the same activeIndex the steps below use. */}
      <motion.div
        variants={fadeUp}
        className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-2)]"
        role="progressbar"
        aria-valuenow={overallPercent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-blue transition-[width] duration-700 ease-out"
          style={{ width: `${overallPercent}%` }}
        />
      </motion.div>

      <motion.ol
        variants={fadeUp}
        className="w-full rounded-[var(--radius-app)] border border-line bg-surface px-4 py-5 text-left sm:px-5"
        aria-live="polite"
      >
        {STAGES.map(({ key, label }, i) => {
          // The backend is genuinely finished once jobStatus is "ok" — show
          // the last step as done rather than still-spinning during the
          // brief pacing dwell before navigating away.
          const done =
            i < activeIndex || (i === activeIndex && i === STAGES.length - 1 && jobStatus?.status === "ok");
          const current = i === activeIndex && !done;
          const isLast = i === STAGES.length - 1;
          return (
            <li key={key} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    "relative flex h-7 w-7 shrink-0 items-center justify-center rounded-full border transition-colors duration-500",
                    done
                      ? "border-[var(--good)] bg-[var(--good)]"
                      : current
                        ? "border-blue bg-paper"
                        : "border-line bg-paper"
                  )}
                  style={current ? { animation: "step-current-pulse 1.8s ease-out infinite" } : undefined}
                >
                  {done ? (
                    <CheckCircle2
                      key={key /* remounts on the done transition, so the pop-in plays exactly once */}
                      size={16}
                      strokeWidth={2}
                      className="text-paper"
                      style={{ animation: "step-check-pop 360ms cubic-bezier(0.34,1.56,0.64,1)" }}
                      aria-hidden="true"
                    />
                  ) : current ? (
                    <Loader2 size={14} strokeWidth={2} className="animate-spin text-blue" aria-hidden="true" />
                  ) : null}
                </span>
                {!isLast && (
                  <span
                    className={cn(
                      "my-0.5 w-px flex-1 transition-colors duration-700",
                      done ? "bg-[var(--good)]" : "bg-line"
                    )}
                    style={{ minHeight: "1.25rem" }}
                    aria-hidden="true"
                  />
                )}
              </div>
              <span
                key={`${key}-${current}` /* replays the slide-in the moment a stage becomes current */}
                className={cn(
                  "pb-4 text-sm leading-relaxed transition-colors duration-500",
                  done ? "text-ink-soft" : current ? "font-medium text-ink" : "text-ink-faint"
                )}
                style={current ? { animation: "step-label-in 300ms ease-out" } : undefined}
              >
                {label}
              </span>
            </li>
          );
        })}
      </motion.ol>
    </motion.div>
  );
}
