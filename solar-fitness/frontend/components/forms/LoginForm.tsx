"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Primitives";
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/fetchClient";
import { ROLE_LANDING, type PortalRole } from "@/lib/auth/session";

const schema = z.object({
  email: z.string().email("Enter a valid work email address."),
  password: z.string().min(6, "Password must be at least 6 characters."),
});
type FormValues = z.infer<typeof schema>;

export function LoginForm({
  defaultEmail = "",
  defaultPassword = "",
}: {
  defaultEmail?: string;
  defaultPassword?: string;
}) {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: defaultEmail, password: defaultPassword },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const session = await login(values.email, values.password);
      router.push(ROLE_LANDING[session.role as PortalRole] ?? "/home");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  });

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
      {formError && (
        <p role="alert" className="text-sm" style={{ color: "var(--bad)" }}>
          {formError}
        </p>
      )}
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
