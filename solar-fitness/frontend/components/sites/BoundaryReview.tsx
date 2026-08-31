"use client";

import { useState } from "react";
import { CheckCircle2, PenLine, XCircle } from "lucide-react";
import { MapView } from "@/components/map/MapView";
import { Button, Card, Badge } from "@/components/ui/Primitives";
import type { Site } from "@/lib/types";

export function BoundaryReview({ site }: { site: Site }) {
  const [decision, setDecision] = useState<"pending" | "accepted" | "adjusted" | "rejected">("pending");

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1.3fr_1fr]">
      <div className="space-y-3">
        <MapView pins={[{ id: site.id, lat: site.location.lat, lng: site.location.lng, label: site.name, verdict: site.latestAssessment?.verdict }]} height={440} drawEnabled />
        <p className="text-xs text-ink-faint">
          Manual drawing tools (terra-draw) render as disabled controls in preview mode — connect a Google Maps API key
          to enable freehand boundary editing.
        </p>
      </div>

      <div className="space-y-4">
        <Card className="p-4">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-sm font-medium text-ink">AI (VIS) boundary suggestion</p>
            <Badge tone="blue">Auto-generated</Badge>
          </div>
          <p className="text-sm text-ink-soft">
            The vision module proposed a roof boundary covering an estimated usable area from the latest satellite
            pass. Review and accept, adjust, or reject before it is used in capacity sizing.
          </p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-sm">
            <div>
              <dt className="text-xs text-ink-faint">Suggested area</dt>
              <dd className="font-mono tabular text-ink">455 m²</dd>
            </div>
            <div>
              <dt className="text-xs text-ink-faint">Confidence</dt>
              <dd className="text-ink">Medium</dd>
            </div>
          </dl>
        </Card>

        <div className="flex flex-wrap gap-2">
          <Button variant="primary" onClick={() => setDecision("accepted")}>
            <CheckCircle2 size={15} strokeWidth={1.75} /> Accept suggestion
          </Button>
          <Button variant="secondary" onClick={() => setDecision("adjusted")}>
            <PenLine size={15} strokeWidth={1.75} /> Adjust manually
          </Button>
          <Button variant="danger" onClick={() => setDecision("rejected")}>
            <XCircle size={15} strokeWidth={1.75} /> Reject
          </Button>
        </div>

        {decision !== "pending" && (
          <Card className="p-3 text-sm" style={{ borderColor: decision === "rejected" ? "var(--bad)" : "var(--good)" }}>
            {decision === "accepted" && "Boundary suggestion accepted and will be used for the next assessment run."}
            {decision === "adjusted" && "Manual adjustment mode would open the drawing tool here (requires a Maps API key)."}
            {decision === "rejected" && "Suggestion rejected. Draw a boundary manually or request a re-run."}
          </Card>
        )}
      </div>
    </div>
  );
}
