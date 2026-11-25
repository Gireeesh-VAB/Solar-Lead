"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Primitives";
import { PasswordInput } from "@/components/ui/PasswordInput";
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
  // Test-credential autofill is a local/dev convenience only — never ship
  // known passwords (even for seeded test accounts) as pre-filled or
  // one-click-fillable values in a production bundle.
  const allowAutofill = process.env.NODE_ENV !== "production";
  const {
    register,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: allowAutofill ? defaultEmail : "",
      password: allowAutofill ? defaultPassword : "",
    },
  });

  const hasAutofill = allowAutofill && Boolean(defaultEmail && defaultPassword);
  const handleAutofill = () => {
    setValue("email", defaultEmail, { shouldValidate: true });
    setValue("password", defaultPassword, { shouldValidate: true });
  };

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const session = await login(values.email, values.password);
      // replace, not push: leaving a "sign in" entry in history means
      // browser/Back-button back from the freshly-loaded dashboard lands
      // an already-authenticated user back on a stale login form.
      router.replace(ROLE_LANDING[session.role as PortalRole] ?? "/home");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      {hasAutofill && (
        <button
          type="button"
          onClick={handleAutofill}
          className="w-full rounded-[var(--radius-app)] border border-dashed border-line px-3 py-1.5 text-xs font-medium text-ink-soft hover:border-blue hover:text-blue"
        >
          Autofill test credentials
        </button>
      )}
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
        <PasswordInput
          id="password"
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
