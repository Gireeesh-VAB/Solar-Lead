import { Box, ImageOff } from "lucide-react";

export function PanoramaViewer({ panoramaUrl, siteName }: { panoramaUrl?: string | null; siteName: string }) {
  if (!panoramaUrl) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-app)] border border-dashed border-line bg-surface py-20 text-center">
        <ImageOff size={28} strokeWidth={1.5} className="text-ink-faint" aria-hidden="true" />
        <div>
          <p className="font-medium text-ink">Panorama not generated</p>
          <p className="mt-1 text-sm text-ink-soft max-w-sm">
            No 3D panorama capture is available for this site yet. Run a field capture or request a panorama render to enable this view.
          </p>
        </div>
      </div>
    );
  }
  return (
    <div className="relative overflow-hidden rounded-[var(--radius-app)] border border-line bg-[var(--surface-2)]">
      <div
        className="flex h-[420px] w-full items-center justify-center"
        style={{
          backgroundImage:
            "repeating-linear-gradient(135deg, var(--surface) 0px, var(--surface) 18px, var(--surface-2) 18px, var(--surface-2) 36px)",
        }}
        aria-label={`3D panorama placeholder for ${siteName}`}
        role="img"
      >
        <div className="flex flex-col items-center gap-2 rounded-[var(--radius-app)] border border-line bg-paper/90 px-5 py-4 text-center shadow-[var(--shadow-float)]">
          <Box size={26} strokeWidth={1.5} className="text-blue" aria-hidden="true" />
          <p className="text-sm font-medium text-ink">3D panorama</p>
          <p className="text-xs text-ink-soft max-w-xs">
            Interactive panorama viewer would render here (@react-three/fiber). Static capture reference: <span className="font-mono">{panoramaUrl}</span>
          </p>
        </div>
      </div>
    </div>
  );
}
