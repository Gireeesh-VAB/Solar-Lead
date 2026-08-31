"use client";

import { MapPin, Power } from "lucide-react";
import { useUpdateVendorAvailability, useVendorProfile } from "@/lib/query/hooks";
import { Card, CardSkeleton, ErrorState, Badge, Button } from "@/components/ui/Primitives";

export function ServiceAreaClient() {
  const profile = useVendorProfile();
  const updateAvailability = useUpdateVendorAvailability();

  if (profile.isLoading) return <CardSkeleton />;
  if (profile.isError) return <ErrorState description="Could not load service area." onRetry={() => profile.refetch()} />;
  if (!profile.data) return null;

  const available = profile.data.availability;

  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-2">
          <Power size={18} strokeWidth={1.75} className={available ? "text-teal" : "text-ink-faint"} aria-hidden="true" />
          <div>
            <p className="font-medium text-ink">{available ? "Available for new jobs" : "Not accepting new jobs"}</p>
            <p className="text-xs text-ink-soft">Toggle to control whether you're assigned new jobs in your service area.</p>
          </div>
        </div>
        <Button
          variant={available ? "secondary" : "primary"}
          onClick={() => updateAvailability.mutate(!available)}
          disabled={updateAvailability.isPending}
        >
          {updateAvailability.isPending ? "Updating…" : available ? "Go unavailable" : "Go available"}
        </Button>
      </Card>

      <Card className="space-y-3 p-4">
        <div className="flex items-center gap-2 text-sm text-ink">
          <MapPin size={15} strokeWidth={1.75} aria-hidden="true" />
          {profile.data.serviceArea.region}
        </div>
        <div className="flex flex-wrap gap-1.5">
          {profile.data.serviceArea.districts.map((d) => (
            <Badge key={d} tone="blue">
              {d}
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}
