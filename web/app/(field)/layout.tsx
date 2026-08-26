import { Sun } from "lucide-react";

export default function FieldLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-paper">
      <header className="flex items-center gap-2 border-b border-line bg-surface px-4 py-3">
        <Sun size={18} strokeWidth={1.75} className="text-amber" aria-hidden="true" />
        <span className="text-sm font-semibold text-ink">Field capture</span>
      </header>
      <main className="px-4 py-5">{children}</main>
    </div>
  );
}
