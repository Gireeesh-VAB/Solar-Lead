"use client";

import { useState } from "react";
import { LayoutGrid, Map as MapIcon } from "lucide-react";
import { MapView, type MapPinData } from "@/components/map/MapView";
import { VerdictChip } from "@/components/ui/VerdictChip";
import { Card, Button } from "@/components/ui/Primitives";
import { formatKwp, siteTypeLabel } from "@/lib/utils";
import type { Site } from "@/lib/types";
import Link from "next/link";

// deck.gl clustering requires a map provider (Google/MapLibre) which is not
// configured in this environment. We fall back to a styled, verdict-colored
// grid — still fully functional for triage — and keep the SVG map preview
// as the geographic view.
export function PortfolioMap({ sites }: { sites: Site[] }) {
  const [view, setView] = useState<"map" | "grid">("map");
  const pins: MapPinData[] = sites.map((s) => ({
    id: s.id,
    lat: s.location.lat,
    lng: s.location.lng,
    label: s.name,
    verdict: s.latestAssessment?.verdict,
  }));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-end gap-1" role="tablist" aria-label="Portfolio view mode">
        <Button
          variant={view === "map" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setView("map")}
          role="tab"
          aria-selected={view === "map"}
        >
          <MapIcon size={14} strokeWidth={1.75} /> Map
        </Button>
        <Button
          variant={view === "grid" ? "secondary" : "ghost"}
          size="sm"
          onClick={() => setView("grid")}
          role="tab"
          aria-selected={view === "grid"}
        >
          <LayoutGrid size={14} strokeWidth={1.75} /> Clustered grid
        </Button>
      </div>
      {view === "map" ? (
        <MapView pins={pins} height={520} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sites.map((s) => (
            <Card key={s.id} className="p-3">
              <Link href={`/sites/${s.id}`} className="font-medium text-ink hover:text-amber">
                {s.name}
              </Link>
              <p className="mt-0.5 text-xs text-ink-soft">
                {s.district}, {s.state} · {siteTypeLabel(s.siteType)}
              </p>
              <div className="mt-2 flex items-center justify-between gap-2">
                {s.latestAssessment ? (
                  <VerdictChip verdict={s.latestAssessment.verdict} size="sm" />
                ) : (
                  <span className="text-xs text-ink-faint">Not assessed</span>
                )}
                {s.latestAssessment && (
                  <span className="font-mono tabular text-xs text-ink-soft">
                    {formatKwp(s.latestAssessment.capacityKwp)}
                  </span>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
