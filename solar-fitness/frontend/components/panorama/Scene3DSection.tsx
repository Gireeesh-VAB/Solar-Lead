"use client";

// The "View roof in 3D" panel on the result page. Uses the shared
// TechnicalDetails collapsible (components/ui/TechnicalDetails.tsx) so this
// panel only mounts — and so useCheckScene() only fetches — once the viewer
// opens it: this section's own hook call lives inside Scene3DPanelContent,
// which TechnicalDetails only renders into the tree when `open` is true.
import { Box, ImageOff, Loader2 } from "lucide-react";
import { TechnicalDetails } from "@/components/ui/TechnicalDetails";
import { Scene3DViewer } from "@/components/panorama/Scene3DViewer";
import { useCheckScene } from "@/lib/query/hooks";

function Scene3DPanelContent({ checkId }: { checkId: string }) {
  const scene = useCheckScene(checkId);

  if (scene.isLoading) {
    return (
      <div className="flex h-[240px] items-center justify-center rounded-[var(--radius-app)] border border-dashed border-line bg-surface-2">
        <Loader2 className="animate-spin text-ink-faint" size={22} aria-hidden="true" />
      </div>
    );
  }

  const data = scene.data;

  if (process.env.NODE_ENV === "development" && data) {
    console.debug("[Scene3DSection] scene loaded", {
      status: data.status,
      reason: data.reason,
      originLat: data.originLat,
      originLng: data.originLng,
      heightM: data.heightM,
      groundSource: data.groundSource,
      panelCount: data.panelCount,
      obstacleCount: data.obstacles.length,
      hasMounting: !!data.mounting,
      version: data.version,
    });
  }

  if (scene.isError || !data || data.status !== "ok" || !data.roof) {
    const message = scene.isError
      ? "Couldn't load the 3D view. Try again in a moment."
      : (data?.reason ?? "3D view isn't available for this check yet.");
    return (
      <div className="flex h-[240px] flex-col items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-surface-2 px-4 text-center">
        <ImageOff className="text-ink-faint" size={22} aria-hidden="true" />
        <p className="text-sm text-ink-soft">{message}</p>
      </div>
    );
  }

  return (
    <Scene3DViewer
      roof={data.roof}
      walls={data.walls}
      panels={data.panels}
      mounting={data.mounting}
      obstacles={data.obstacles}
    />
  );
}

export function Scene3DSection({ checkId }: { checkId: string }) {
  return (
    <TechnicalDetails label="View roof in 3D" icon={Box}>
      <Scene3DPanelContent checkId={checkId} />
    </TechnicalDetails>
  );
}
