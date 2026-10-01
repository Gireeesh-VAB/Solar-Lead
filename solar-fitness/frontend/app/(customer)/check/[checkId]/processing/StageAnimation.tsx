"use client";

// One bespoke, looping animated scene per real pipeline stage
// (routers/assessments.py::ASSESSMENT_STAGES) — swapped as the backend's
// actual progress advances, not a generic spinner standing in for all
// eight. Pure SVG + CSS keyframes (see app/globals.css's "Processing-page
// stage visuals" block) — no animation library, matching this app's
// "don't add a dependency for something CSS already does" discipline.
// Each scene is deliberately a literal, legible sketch of what that stage
// is actually doing (a pin resolving, a scan line reading the roof, a
// gauge sizing the system, panels dropping into place, a report
// assembling) rather than an abstract loader.

import { useEffect, useRef, useState } from "react";
import type { AssessmentStage } from "@/lib/api/client";

// Real footage (public/videos/rooftop-processing.mp4 — a single aerial
// clip of one rooftop: pin drop -> scan -> obstacle boxes -> capacity
// panel -> panel tiling -> gauges) stands in for the SVG sketch on every
// stage it actually depicts. Each stage owns a [start, end) slice of the
// SAME clip rather than a separate file per stage, so the one building
// stays visually continuous across stages exactly like the real pipeline
// analyzes one real roof throughout. Seconds, matching the file as
// encoded (crop only touches frame height, never the time axis).
//
// finalizing_result is deliberately absent — the clip ends on the scoring
// gauges and has no sunlight->panel->inverter->house->grid finale, so
// that stage keeps FinalizingResultScene below rather than inventing
// footage that was never shot.
// Exported so ProcessingClient's step pacer can dwell on each stage for
// roughly as long as that stage's own footage actually plays — pacing
// faster than this cuts every video segment off before it can play,
// which is what "jumping" looked like before this was wired up.
export const VIDEO_STAGE_RANGES: Partial<Record<AssessmentStage, [number, number]>> = {
  resolving_location: [0, 1.5],
  analyzing_roof_imagery: [1.5, 4.5],
  detecting_obstacles: [4.5, 8.0],
  computing_usable_area: [8.0, 9.5],
  sizing_system: [9.5, 11.0],
  placing_panels: [11.0, 14.5],
  scoring_feasibility: [14.5, 15.0],
};

const VIDEO_SRC = "/videos/rooftop-processing.mp4";

/** Plays exactly this stage's slice of the shared clip and holds on its
 * last frame — never bleeding into the next stage's footage before the
 * backend actually reports that stage, the same "don't get ahead of real
 * progress" discipline StageAnimation's remount-per-stage already
 * enforces for the SVG scenes. Falls back to `Fallback` (that stage's own
 * SVG scene) if the video can't play at all, so a blocked/unsupported
 * video never leaves a dead box on screen. */
function VideoStageScene({
  range,
  Fallback,
}: {
  range: [number, number];
  Fallback: () => React.JSX.Element;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [failed, setFailed] = useState(false);
  const [start, end] = range;

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const playSegment = () => {
      video.currentTime = start;
      void video.play().catch(() => setFailed(true));
    };
    const holdAtEnd = () => {
      if (video.currentTime >= end) video.pause();
    };

    video.addEventListener("timeupdate", holdAtEnd);
    if (video.readyState >= 1) {
      playSegment();
    } else {
      video.addEventListener("loadedmetadata", playSegment, { once: true });
    }
    return () => {
      video.removeEventListener("timeupdate", holdAtEnd);
      video.removeEventListener("loadedmetadata", playSegment);
    };
  }, [start, end]);

  if (failed) return <Fallback />;

  return (
    <div
      className="h-full w-full overflow-hidden rounded-[calc(var(--radius-app)-4px)]"
      style={{ animation: "stage-scene-in 420ms cubic-bezier(0.16,1,0.3,1)" }}
    >
      <video
        ref={videoRef}
        src={VIDEO_SRC}
        muted
        playsInline
        preload="auto"
        aria-hidden="true"
        className="h-full w-full object-cover"
        onError={() => setFailed(true)}
      />
    </div>
  );
}

function Scene({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 240 150"
      className="stage-scene h-full w-full"
      style={{ animation: "stage-scene-in 420ms cubic-bezier(0.16,1,0.3,1)" }}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function ResolvingLocationScene() {
  return (
    <Scene>
      {/* Faint coordinate grid — this is a map being searched. */}
      <g stroke="var(--line)" strokeWidth="1" opacity="0.6">
        {[30, 70, 110, 150, 190, 210].map((x) => (
          <line key={`v${x}`} x1={x} y1="10" x2={x} y2="140" />
        ))}
        {[30, 60, 90, 120].map((y) => (
          <line key={`h${y}`} x1="10" y1={y} x2="230" y2={y} />
        ))}
      </g>
      {/* Radar rings pinging outward from the resolved point. */}
      {[0, 0.6, 1.2].map((delay) => (
        <circle
          key={delay}
          cx="120"
          cy="78"
          r="34"
          fill="none"
          stroke="var(--blue)"
          strokeWidth="2"
          style={{
            transformOrigin: "120px 78px",
            animation: `radar-ping 1.8s ease-out ${delay}s infinite`,
          }}
        />
      ))}
      {/* The pin itself, dropping and settling. */}
      <g style={{ transformOrigin: "120px 60px", animation: "pin-drop 700ms cubic-bezier(0.34,1.56,0.64,1) 200ms both" }}>
        <path
          d="M120 40c-9 0-16 7-16 16 0 12 16 30 16 30s16-18 16-30c0-9-7-16-16-16z"
          fill="var(--brand)"
        />
        <circle cx="120" cy="56" r="5.5" fill="var(--paper)" />
      </g>
    </Scene>
  );
}

function AnalyzingRoofImageryScene() {
  return (
    <Scene>
      <defs>
        <linearGradient id="scan-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--blue)" stopOpacity="0" />
          <stop offset="50%" stopColor="var(--blue)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--blue)" stopOpacity="0" />
        </linearGradient>
        <clipPath id="roof-clip">
          <path d="M60 110 L60 70 L120 35 L180 70 L180 110 Z" />
        </clipPath>
      </defs>
      {/* The rooftop being read. */}
      <path
        d="M60 110 L60 70 L120 35 L180 70 L180 110 Z"
        fill="var(--surface-2)"
        stroke="var(--slate)"
        strokeWidth="1.5"
      />
      <g clipPath="url(#roof-clip)">
        <rect x="45" y="0" width="150" height="30" fill="url(#scan-grad)" style={{ animation: "scan-sweep 1.6s ease-in-out infinite" }} />
      </g>
      <path d="M60 110 L60 70 L120 35 L180 70 L180 110 Z" fill="none" stroke="var(--blue)" strokeWidth="1.5" opacity="0.5" />
    </Scene>
  );
}

function DetectingObstaclesScene() {
  return (
    <Scene>
      <path d="M60 112 L60 68 L120 34 L180 68 L180 112 Z" fill="var(--surface-2)" stroke="var(--slate)" strokeWidth="1.5" />
      {/* Water tank */}
      <g style={{ transformOrigin: "95px 90px", animation: "obstacle-flag 2.4s ease-in-out 0.1s infinite" }}>
        <rect x="86" y="80" width="18" height="16" rx="2" fill="var(--teal)" />
        <circle cx="95" cy="80" r="9" fill="var(--teal-soft)" />
      </g>
      {/* AC unit */}
      <g style={{ transformOrigin: "150px 95px", animation: "obstacle-flag 2.4s ease-in-out 0.9s infinite" }}>
        <rect x="136" y="88" width="28" height="14" rx="2" fill="var(--amber-soft)" />
        <line x1="140" y1="92" x2="160" y2="92" stroke="var(--paper)" strokeWidth="1.5" />
        <line x1="140" y1="97" x2="160" y2="97" stroke="var(--paper)" strokeWidth="1.5" />
      </g>
      {/* A detection reticle sweeping across, tagging each obstacle. */}
      <g style={{ animation: "obstacle-flag 2.4s ease-in-out 0.5s infinite" }}>
        <rect x="80" y="74" width="30" height="26" rx="3" fill="none" stroke="var(--bad)" strokeWidth="1.5" strokeDasharray="4 3" />
      </g>
      <g style={{ animation: "obstacle-flag 2.4s ease-in-out 1.3s infinite" }}>
        <rect x="132" y="82" width="36" height="24" rx="3" fill="none" stroke="var(--bad)" strokeWidth="1.5" strokeDasharray="4 3" />
      </g>
    </Scene>
  );
}

function ComputingUsableAreaScene() {
  const outline = "M55 115 L55 66 L120 30 L185 66 L185 115 L140 115 L140 95 L100 95 L100 115 Z";
  return (
    <Scene>
      <defs>
        <clipPath id="usable-clip">
          <path d={outline} />
        </clipPath>
      </defs>
      <path d={outline} fill="none" stroke="var(--line)" strokeWidth="1" />
      <path
        d={outline}
        fill="none"
        stroke="var(--blue)"
        strokeWidth="2.5"
        strokeDasharray="480"
        style={{ animation: "draw-outline 1.4s ease-out forwards", ["--outline-length" as string]: 480 }}
      />
      <g clipPath="url(#usable-clip)">
        <rect
          x="40"
          y="30"
          width="160"
          height="90"
          fill="var(--good)"
          opacity="0.35"
          style={{ transformOrigin: "120px 120px", animation: "area-fill-sweep 900ms ease-out 1.1s both" }}
        />
      </g>
      {/* The excluded notch (an obstacle setback) stays visibly outside the fill. */}
      <rect x="100" y="95" width="40" height="20" fill="var(--paper)" opacity="0.001" />
    </Scene>
  );
}

function SizingSystemScene() {
  const [kwp, setKwp] = useState(0);
  useEffect(() => {
    const target = 6.4;
    const start = performance.now();
    const duration = 1400;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setKwp(Number((target * (1 - Math.pow(1 - t, 3))).toFixed(1)));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const radius = 46;
  const circumference = 2 * Math.PI * radius * 0.75; // 270-degree arc
  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <svg viewBox="0 0 140 140" className="stage-scene h-full w-full" style={{ animation: "stage-scene-in 420ms cubic-bezier(0.16,1,0.3,1)" }} aria-hidden="true">
        <g transform="rotate(135 70 70)">
          <circle cx="70" cy="70" r={radius} fill="none" stroke="var(--surface-2)" strokeWidth="10" strokeDasharray={`${circumference} 999`} strokeLinecap="round" />
          <circle
            cx="70"
            cy="70"
            r={radius}
            fill="none"
            stroke="var(--amber)"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${circumference} 999`}
            style={{
              animation: "gauge-sweep 1.4s cubic-bezier(0.16,1,0.3,1) forwards",
              ["--gauge-full" as string]: circumference,
              ["--gauge-target" as string]: circumference * 0.28,
            }}
          />
        </g>
      </svg>
      <div className="absolute flex flex-col items-center" style={{ animation: "counter-tick 200ms linear" }}>
        <span className="text-2xl font-semibold tabular text-ink">{kwp.toFixed(1)}</span>
        <span className="text-[10px] font-medium uppercase tracking-wide text-ink-faint">kWp sizing</span>
      </div>
    </div>
  );
}

function PlacingPanelsScene() {
  const cols = 4;
  const rows = 3;
  const cells = Array.from({ length: cols * rows }, (_, i) => i);
  return (
    <Scene>
      <path d="M55 118 L55 62 L120 28 L185 62 L185 118 Z" fill="var(--surface-2)" stroke="var(--slate)" strokeWidth="1.5" />
      <g>
        {cells.map((i) => {
          const col = i % cols;
          const row = Math.floor(i / cols);
          const x = 70 + col * 26;
          const y = 68 + row * 16;
          const delay = (row * cols + col) * 90;
          return (
            <g key={i} style={{ transformOrigin: `${x + 10}px ${y + 6}px`, animation: `panel-drop-in 420ms cubic-bezier(0.34,1.56,0.64,1) ${delay}ms both` }}>
              <rect x={x} y={y} width="21" height="12" rx="1.5" fill="var(--blue)" />
              <rect
                x={x}
                y={y}
                width="21"
                height="12"
                rx="1.5"
                fill="var(--paper)"
                style={{ animation: `panel-glint 2.2s ease-in-out ${delay + 500}ms infinite` }}
              />
            </g>
          );
        })}
      </g>
    </Scene>
  );
}

function ScoringFeasibilityScene() {
  return (
    <div className="relative flex h-full w-full items-center justify-center">
      <svg viewBox="0 0 160 110" className="stage-scene h-full w-full" style={{ animation: "stage-scene-in 420ms cubic-bezier(0.16,1,0.3,1)" }} aria-hidden="true">
        <defs>
          <linearGradient id="meter-grad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="var(--bad)" />
            <stop offset="50%" stopColor="var(--warn)" />
            <stop offset="100%" stopColor="var(--good)" />
          </linearGradient>
        </defs>
        <path d="M20 90 A60 60 0 0 1 140 90" fill="none" stroke="url(#meter-grad)" strokeWidth="12" strokeLinecap="round" />
        <g style={{ transformOrigin: "80px 90px", animation: "needle-sweep 1.3s cubic-bezier(0.16,1,0.3,1) forwards", ["--needle-from" as string]: "-90deg", ["--needle-to" as string]: "42deg" }}>
          <line x1="80" y1="90" x2="80" y2="38" stroke="var(--ink)" strokeWidth="3" strokeLinecap="round" />
          <circle cx="80" cy="90" r="5" fill="var(--ink)" />
        </g>
      </svg>
      <div
        className="absolute bottom-1 flex h-7 w-7 items-center justify-center rounded-full"
        style={{ background: "var(--good)", animation: "badge-pop 500ms cubic-bezier(0.34,1.56,0.64,1) 1.2s both" }}
      >
        <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="var(--paper)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="4,13 9,18 20,6" />
        </svg>
      </div>
    </div>
  );
}

function FinalizingResultScene() {
  const lines = [0.9, 0.65, 0.8, 0.4];
  return (
    <Scene>
      <rect x="55" y="18" width="130" height="114" rx="6" fill="var(--surface)" stroke="var(--line)" strokeWidth="1.5" />
      <line x1="55" y1="42" x2="185" y2="42" stroke="var(--line)" strokeWidth="1" />
      {lines.map((w, i) => (
        <rect
          key={i}
          x="68"
          y={54 + i * 14}
          width={110 * w}
          height="6"
          rx="3"
          fill="var(--slate-soft)"
          style={{ transformOrigin: "68px 0px", animation: `line-write 380ms ease-out ${i * 160}ms both` }}
        />
      ))}
      <g style={{ transformOrigin: "150px 112px" }}>
        {[0, 1].map((i) => (
          <circle
            key={i}
            cx="150"
            cy="112"
            r="14"
            fill="none"
            stroke="var(--good)"
            strokeWidth="2"
            style={{ animation: `burst-ring 1.1s ease-out ${640 + i * 200}ms both` }}
          />
        ))}
        <circle cx="150" cy="112" r="13" fill="var(--good)" style={{ animation: "report-check-burst 480ms cubic-bezier(0.34,1.56,0.64,1) 700ms both" }} />
        <polyline
          points="144,112 148,117 157,106"
          fill="none"
          stroke="var(--paper)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ animation: "report-check-burst 480ms cubic-bezier(0.34,1.56,0.64,1) 700ms both" }}
        />
      </g>
    </Scene>
  );
}

const SCENES: Record<AssessmentStage, () => React.JSX.Element> = {
  resolving_location: ResolvingLocationScene,
  analyzing_roof_imagery: AnalyzingRoofImageryScene,
  detecting_obstacles: DetectingObstaclesScene,
  computing_usable_area: ComputingUsableAreaScene,
  sizing_system: SizingSystemScene,
  placing_panels: PlacingPanelsScene,
  scoring_feasibility: ScoringFeasibilityScene,
  finalizing_result: FinalizingResultScene,
};

export function StageAnimation({ stage }: { stage: AssessmentStage }) {
  const SceneComponent = SCENES[stage] ?? ResolvingLocationScene;
  const videoRange = VIDEO_STAGE_RANGES[stage];
  return (
    <div className="flex h-40 w-full items-center justify-center rounded-[var(--radius-app)] border border-line bg-paper p-3 sm:h-44">
      {/* Remounting on stage change is deliberate — each scene's entrance
          keyframes (drop-in, draw-on, sweep) should replay from the start
          every time the backend actually moves to that stage, not resume
          mid-animation from a previous mount. Same reasoning extends the
          video path: a fresh mount re-seeks/re-plays its slice rather than
          resuming wherever a previous stage's <video> happened to be. */}
      <div key={stage} className="h-full w-full">
        {videoRange ? (
          <VideoStageScene range={videoRange} Fallback={SceneComponent} />
        ) : (
          <SceneComponent />
        )}
      </div>
    </div>
  );
}
