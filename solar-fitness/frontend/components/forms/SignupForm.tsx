"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Primitives";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { signup } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/fetchClient";
import { ROLE_LANDING, type PortalRole } from "@/lib/auth/session";
import { requiredIndianPhone, sanitizePhoneInput } from "@/lib/validation/phone";

const schema = z.object({
  name: z.string().min(2, "Enter your name."),
  email: z.string().email("Enter a valid email address."),
  phone: requiredIndianPhone,
  // Matches the backend's MIN_PASSWORD_LENGTH (app_auth.py) — a shorter
  // client-side minimum let a 6-7 char password pass here and then get
  // rejected by the server on submit.
  password: z.string().min(8, "Password must be at least 8 characters."),
});
type FormValues = z.infer<typeof schema>;

export function SignupForm() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    trigger,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", email: "", phone: "", password: "" },
  });

  const onSubmit = handleSubmit(async (values) => {
    setSubmitting(true);
    setFormError(null);
    try {
      const session = await signup(values);
      // replace, not push — see LoginForm's own onSubmit for why.
      router.replace(ROLE_LANDING[session.role as PortalRole] ?? "/home");
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
      setSubmitting(false);
    }
  });

  return (
    <form onSubmit={onSubmit} className="space-y-4" noValidate>
      <div>
        <label htmlFor="name" className="mb-1 block text-sm font-medium text-ink">
          Full name
        </label>
        <input
          id="name"
          type="text"
          autoComplete="name"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? "name-error" : undefined}
          {...register("name")}
        />
        {errors.name && (
          <p id="name-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.name.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink">
          Email
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
        <label htmlFor="phone" className="mb-1 block text-sm font-medium text-ink">
          Phone
        </label>
        <input
          id="phone"
          type="tel"
          inputMode="numeric"
          autoComplete="tel"
          className="w-full rounded-[var(--radius-app)] border border-line bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-blue"
          aria-invalid={!!errors.phone}
          aria-describedby={errors.phone ? "phone-error" : undefined}
          {...register("phone", {
            onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
              e.target.value = sanitizePhoneInput(e.target.value);
              void trigger("phone");
            },
          })}
        />
        {errors.phone && (
          <p id="phone-error" className="mt-1 text-xs" style={{ color: "var(--bad)" }}>
            {errors.phone.message}
          </p>
        )}
      </div>
      <div>
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink">
          Password
        </label>
        <PasswordInput
          id="password"
          autoComplete="new-password"
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
        {submitting ? "Creating your account…" : "Create account"}
      </Button>
    </form>
  );
}
