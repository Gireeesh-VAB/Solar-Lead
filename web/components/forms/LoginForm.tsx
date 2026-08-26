"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { KeyRound, Building2, HardHat, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/Primitives";
import { cn } from "@/lib/utils";

const schema = z.object({
  email: z.string().email("Enter a valid work email address."),
  password: z.string().min(6, "Password must be at least 6 characters."),
});
type FormValues = z.infer<typeof schema>;

const DEMO_EMAIL = "analyst@demo-agency.gov.in";
const DEMO_PASSWORD = "demo-1234";

type PortalRole = "customer" | "vendor" | "admin";

const ROLE_LANDING: Record<PortalRole, string> = {
  customer: "/home",
  vendor: "/vendor/dashboard",
  admin: "/admin/dashboard",
};

const ROLE_OPTIONS: { role: PortalRole; label: string; icon: typeof Building2 }[] = [
  { role: "customer", label: "Customer", icon: Building2 },
  { role: "vendor", label: "Vendor", icon: HardHat },
  { role: "admin", label: "Admin", icon: ShieldCheck },
];

export function LoginForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [role, setRole] = useState<PortalRole>("customer");
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "" },
  });

  const onSubmit = handleSubmit(async () => {
    setSubmitting(true);
    await new Promise((r) => setTimeout(r, 500));
    router.push(ROLE_LANDING[role]);
  });

  const applyDemoCredentials = (targetRole: PortalRole = role) => {
    setRole(targetRole);
    setValue("email", DEMO_EMAIL, { shouldValidate: true });
    setValue("password", DEMO_PASSWORD, { shouldValidate: true });
    void handleSubmit(async () => {
      setSubmitting(true);
      await new Promise((r) => setTimeout(r, 500));
      router.push(ROLE_LANDING[targetRole]);
    })();
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div>
        <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink">
          Work email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="email"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
          aria-invalid={!!errors.email}
          aria-describedby={errors.email ? "email-error" : undefined}
          {...register("email")}
        />
        {errors.email && (
          <p id="email-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.email.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
          aria-invalid={!!errors.password}
          aria-describedby={errors.password ? "password-error" : undefined}
          {...register("password")}
        />
        {errors.password && (
          <p id="password-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.password.message}
          </p>
        )}
      </div>
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? "Signing in…" : "Sign in"}
      </Button>

      <div className="relative flex items-center py-1" aria-hidden="true">
        <div className="h-px flex-1 bg-line" />
        <span className="px-2 text-[11px] uppercase tracking-wide text-ink-faint">or</span>
        <div className="h-px flex-1 bg-line" />
      </div>

      <fieldset className="space-y-1.5">
        <legend className="mb-1 text-xs font-medium text-ink-soft">Demo portal</legend>
        <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Portal to demo">
          {ROLE_OPTIONS.map(({ role: r, label, icon: Icon }) => (
            <button
              key={r}
              type="button"
              role="radio"
              aria-checked={role === r}
              onClick={() => setRole(r)}
              disabled={submitting}
              className={cn(
                "flex flex-col items-center gap-1 rounded-[var(--radius-app)] border px-2 py-2 text-xs font-medium outline-none transition-colors disabled:opacity-60",
                role === r ? "border-blue bg-surface-2 text-ink" : "border-line text-ink-soft hover:border-blue hover:text-ink"
              )}
            >
              <Icon size={16} strokeWidth={1.75} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
      </fieldset>

      <button
        type="button"
        onClick={() => applyDemoCredentials()}
        disabled={submitting}
        className="flex w-full items-center justify-center gap-2 rounded-[var(--radius-app)] border border-dashed border-line bg-paper px-3 py-2 text-sm font-medium text-blue outline-none transition-colors hover:border-blue hover:bg-surface focus-visible:border-blue disabled:opacity-60"
      >
        <KeyRound size={15} strokeWidth={1.75} aria-hidden="true" />
        {submitting ? "Signing in…" : `Use demo credentials — ${ROLE_OPTIONS.find((o) => o.role === role)?.label}`}
      </button>

      <p className="text-center text-xs text-ink-faint">
        Demo build — any password of 6+ characters signs you in against mock data. Pick a portal above to control where the demo lands.
      </p>
    </form>
  );
}
