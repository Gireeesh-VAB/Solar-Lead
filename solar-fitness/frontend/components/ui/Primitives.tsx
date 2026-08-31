import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[var(--radius-app)] border border-line bg-surface", className)}
      {...props}
    />
  );
}

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
}) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-app)] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed";
  const sizeCls = size === "sm" ? "px-2.5 py-1.5 text-xs" : "px-3.5 py-2 text-sm";
  const variants: Record<string, string> = {
    primary: "bg-amber text-white hover:bg-amber-soft",
    secondary: "bg-surface-2 text-ink border border-line hover:bg-surface",
    ghost: "text-ink-soft hover:text-ink hover:bg-surface-2",
    danger: "bg-bad text-white hover:opacity-90",
  };
  return <button className={cn(base, sizeCls, variants[variant], className)} {...props} />;
}

export function Badge({ children, className, tone = "neutral" }: { children: ReactNode; className?: string; tone?: "neutral" | "blue" | "amber" }) {
  const toneCls =
    tone === "blue"
      ? "bg-surface-2 text-blue"
      : tone === "amber"
      ? "bg-surface-2 text-amber"
      : "bg-surface-2 text-ink-soft";
  return (
    <span className={cn("inline-flex items-center rounded-[3px] px-1.5 py-0.5 text-[11px] font-medium", toneCls, className)}>
      {children}
    </span>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line pb-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">{title}</h1>
        {description && <p className="mt-1 text-sm text-ink-soft max-w-2xl">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-[var(--radius-app)] bg-surface-2", className)} />;
}

export function TableSkeleton({ rows = 8, cols = 6 }: { rows?: number; cols?: number }) {
  return (
    <div className="w-full" role="status" aria-label="Loading table data">
      <div className="border-b border-line pb-2 mb-2 flex gap-4">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-4 flex-1" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex gap-4 py-2.5 border-b border-line/60">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} className="h-4 flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <Card className={cn("p-4 space-y-3", className)}>
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-4/5" />
    </Card>
  );
}

export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-app)] border border-dashed border-line py-16 text-center px-6">
      {icon && <div className="text-ink-faint" aria-hidden="true">{icon}</div>}
      <div>
        <p className="font-medium text-ink">{title}</p>
        {description && <p className="mt-1 text-sm text-ink-soft max-w-sm">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center gap-3 rounded-[var(--radius-app)] border py-16 text-center px-6"
      style={{ borderColor: "var(--bad)", background: "var(--bad-bg)" }}
      role="alert"
    >
      <div>
        <p className="font-medium" style={{ color: "var(--bad)" }}>{title}</p>
        {description && <p className="mt-1 text-sm text-ink-soft max-w-sm">{description}</p>}
      </div>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}
