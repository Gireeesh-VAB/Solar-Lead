"use client";

// The vendor Settings page — seven independent sections, each owning its
// own save action (see the plan's reasoning: password/notifications/
// availability/theme are unrelated concerns and shouldn't share one
// submit button). Forms are hand-rolled inline (react-hook-form + zod +
// the same `inputClass` string), matching app/(customer)/profile/
// ProfileForm.tsx's pattern — there's no shared input/toggle/tabs
// component in components/ui/Primitives.tsx to import instead.

import { useState, useSyncExternalStore } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  Bell,
  Check,
  Eye,
  EyeOff,
  IdCard,
  Lock,
  LogOut,
  MapPin,
  Monitor,
  Moon,
  Power,
  Sun,
  Wallet,
} from "lucide-react";
import { Button, Card, CardSkeleton, ErrorState } from "@/components/ui/Primitives";
import {
  useChangePassword,
  useUpdateVendorAvailability,
  useUpdateVendorNotificationPreferences,
  useVendorNotificationPreferences,
  useVendorProfile,
} from "@/lib/query/hooks";
import { ApiError } from "@/lib/api/client";
import { logout } from "@/lib/api/auth";
import { getStoredSession } from "@/lib/auth/session";
import { setTheme, useThemePreference, type ThemePreference } from "@/lib/theme-client";
import { useUnsavedChangesWarning } from "@/lib/hooks/useUnsavedChangesWarning";
import type { VendorNotificationPreferences } from "@/lib/types";

const inputClass =
  "w-full min-h-[44px] rounded-[var(--radius-app)] border border-line bg-paper px-3.5 py-2.5 text-sm text-ink outline-none transition-colors focus:border-blue";

function SectionHeading({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
        style={{ background: "var(--surface-2)", color: "var(--blue)" }}
        aria-hidden="true"
      >
        {icon}
      </span>
      <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-faint">{title}</h2>
    </div>
  );
}

function ReadOnlyField({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ink-faint">{label}</p>
      <p className="min-h-[24px] text-sm text-ink">{value || "—"}</p>
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
    </div>
  );
}

// -----------------------------------------------------------------------------
// 1. Account Information — entirely read-only, no backend endpoint
// exists to edit any vendor identity field.
// -----------------------------------------------------------------------------

// Session email never changes while this page is open (there's no login
// flow reachable from here), so this never needs to notify a listener —
// only useSyncExternalStore's hydration-safety (real value only once
// mounted client-side, matching lib/i18n/LanguageContext.tsx's pattern,
// never a useState+useEffect(setState) that would trip
// react-hooks/set-state-in-effect).
function noopSubscribe(): () => void {
  return () => {};
}

function AccountInformationSection() {
  const profile = useVendorProfile();
  const email = useSyncExternalStore(
    noopSubscribe,
    () => getStoredSession()?.email ?? null,
    () => null
  );

  return (
    <section aria-labelledby="account-info-heading">
      <Card className="space-y-5 p-5 sm:p-6">
        <SectionHeading icon={<IdCard size={15} strokeWidth={1.75} />} title="Account information" />
        {profile.isLoading && <CardSkeleton className="border-none p-0" />}
        {profile.isError && <ErrorState description="Could not load account information." onRetry={() => profile.refetch()} />}
        {profile.data && (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <ReadOnlyField label="Business name" value={profile.data.name} />
              <ReadOnlyField label="Registered email" value={email ?? "—"} />
              <ReadOnlyField label="Phone number" value={profile.data.contactPhone ?? "—"} />
              <ReadOnlyField label="Vendor ID" value={profile.data.vendorId} />
              <ReadOnlyField
                label="Verification status"
                value={
                  profile.data.verificationStatus.charAt(0).toUpperCase() +
                  profile.data.verificationStatus.slice(1)
                }
              />
            </div>
            <p className="text-xs text-ink-soft">
              These fields are read-only — contact support to update your account information.
            </p>
          </>
        )}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 2. Password & Security
// -----------------------------------------------------------------------------

const passwordSchema = z
  .object({
    currentPassword: z.string().min(1, "Enter your current password."),
    newPassword: z.string().min(8, "New password must be at least 8 characters."),
    confirmPassword: z.string().min(1, "Confirm your new password."),
  })
  .refine((v) => v.newPassword === v.confirmPassword, {
    message: "Passwords don't match.",
    path: ["confirmPassword"],
  });
type PasswordFormValues = z.infer<typeof passwordSchema>;

function passwordStrength(password: string): { label: string; color: string } {
  if (!password) return { label: "", color: "var(--ink-faint)" };
  let score = 0;
  if (password.length >= 8) score++;
  if (password.length >= 12) score++;
  if (/[A-Z]/.test(password) && /[a-z]/.test(password)) score++;
  if (/[0-9]/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;
  if (score <= 2) return { label: "Weak", color: "var(--bad)" };
  if (score <= 3) return { label: "Fair", color: "var(--warn)" };
  return { label: "Strong", color: "var(--good)" };
}

function PasswordField({
  id,
  label,
  autoComplete,
  register,
  error,
}: {
  id: "currentPassword" | "newPassword" | "confirmPassword";
  label: string;
  autoComplete: string;
  register: ReturnType<typeof useForm<PasswordFormValues>>["register"];
  error?: string;
}) {
  const [visible, setVisible] = useState(false);
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          className={`${inputClass} pr-10`}
          aria-invalid={!!error}
          {...register(id)}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
          aria-label={visible ? `Hide ${label.toLowerCase()}` : `Show ${label.toLowerCase()}`}
        >
          {visible ? <EyeOff size={16} strokeWidth={1.75} /> : <Eye size={16} strokeWidth={1.75} />}
        </button>
      </div>
      {error && (
        <p className="mt-1.5 text-xs" style={{ color: "var(--bad)" }}>
          {error}
        </p>
      )}
    </div>
  );
}

function PasswordSection() {
  const router = useRouter();
  const changePassword = useChangePassword();
  const [saved, setSaved] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors, isDirty },
  } = useForm<PasswordFormValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });
  const newPassword = watch("newPassword");
  const strength = passwordStrength(newPassword);

  useUnsavedChangesWarning(isDirty && !saved);

  const onSubmit = handleSubmit(async (values) => {
    setSaved(false);
    setServerError(null);
    try {
      await changePassword.mutateAsync({
        currentPassword: values.currentPassword,
        newPassword: values.newPassword,
      });
      // Never let the submitted password linger in form state longer
      // than the request itself needs it.
      reset({ currentPassword: "", newPassword: "", confirmPassword: "" });
      setSaved(true);
    } catch (err) {
      setServerError(
        err instanceof ApiError && err.status === 401
          ? "Current password is incorrect."
          : "Could not change your password. Try again."
      );
    }
  });

  return (
    <section aria-labelledby="password-heading">
      <Card className="space-y-5 p-5 sm:p-6">
        <SectionHeading icon={<Lock size={15} strokeWidth={1.75} />} title="Password & security" />
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <PasswordField id="currentPassword" label="Current password" autoComplete="current-password" register={register} error={errors.currentPassword?.message} />
          <PasswordField id="newPassword" label="New password" autoComplete="new-password" register={register} error={errors.newPassword?.message} />
          {newPassword && (
            <p className="-mt-2 text-xs" style={{ color: strength.color }}>
              Strength: {strength.label}
            </p>
          )}
          <PasswordField id="confirmPassword" label="Confirm new password" autoComplete="new-password" register={register} error={errors.confirmPassword?.message} />

          {serverError && (
            <p className="flex items-center gap-1.5 text-xs" style={{ color: "var(--bad)" }} role="alert">
              <AlertTriangle size={13} strokeWidth={1.75} aria-hidden="true" />
              {serverError}
            </p>
          )}

          <div className="flex flex-col items-stretch gap-2.5 border-t border-line pt-4 sm:flex-row sm:items-center">
            <Button type="submit" disabled={changePassword.isPending} className="w-full sm:w-auto">
              {changePassword.isPending ? "Updating…" : "Change password"}
            </Button>
            {saved && !changePassword.isPending && (
              <span className="flex items-center justify-center gap-1 text-xs sm:justify-start" style={{ color: "var(--good)" }}>
                <Check size={14} strokeWidth={1.75} aria-hidden="true" />
                Password changed
              </span>
            )}
          </div>
        </form>

        <div className="flex items-center justify-between gap-3 border-t border-line pt-5">
          <div>
            <p className="text-sm font-medium text-ink">Log out</p>
            <p className="mt-0.5 text-xs text-ink-soft">Ends your session on this device.</p>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              logout();
              router.replace("/login");
            }}
          >
            <LogOut size={14} strokeWidth={1.75} aria-hidden="true" />
            Log out
          </Button>
        </div>
        {/* No "log out all sessions" control: this app's auth is a stateless
            bearer token with no server-side session/revocation store, so
            there is no other device's session to actually end from here. */}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 3. Notification Preferences — each toggle saves immediately, same
// pattern as the Availability toggle below.
// -----------------------------------------------------------------------------

const NOTIFICATION_TOGGLES: { key: keyof VendorNotificationPreferences; label: string; description: string }[] = [
  { key: "newJobAssignment", label: "New job assignment", description: "When a survey job is assigned to you." },
  { key: "jobDeadlineReminders", label: "Job deadline reminders", description: "As a job's SLA deadline approaches." },
  { key: "jobReassignment", label: "Job reassignment", description: "When a job is reassigned away from you after missing a deadline." },
  { key: "submissionAndPayoutUpdates", label: "Submission & payout updates", description: "When a submission is reconciled or a payout status changes." },
  { key: "disputeUpdates", label: "Dispute updates", description: "When a measurement dispute you raised is updated." },
  { key: "installationUpdates", label: "Installation updates", description: "Progress on installation projects tied to your jobs." },
];

function ToggleSwitch({ checked, onChange, disabled }: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    // The track is 28px tall, well under the ~44px minimum comfortable
    // tap target — this padding widens the actual hit area to that
    // without changing how the switch looks.
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={onChange}
      disabled={disabled}
      className="relative shrink-0 rounded-full p-2.5 -m-2.5 disabled:opacity-50"
    >
      <span
        aria-hidden
        className="relative block h-7 w-12 rounded-full transition-colors duration-150"
        style={{ background: checked ? "var(--amber)" : "var(--surface-2)" }}
      >
        {/* `left-0` is load-bearing, not decorative: with left unset, an
            absolutely-positioned box with no `left`/`right` falls back to
            its CSS "static position", which on this <button> resolves
            using the browser's default button text-align:center rather
            than flush-left — pushing the knob's own baseline right before
            the slide transform below is even applied, and detaching it
            from the track entirely once checked. Pinning left:0 makes the
            position deterministic regardless of any inherited
            text-align. */}
        <span
          className="absolute left-0 top-0.5 h-6 w-6 rounded-full bg-white shadow transition-transform duration-150"
          style={{ transform: checked ? "translateX(22px)" : "translateX(2px)" }}
        />
      </span>
    </button>
  );
}

function NotificationPreferencesSection() {
  const prefs = useVendorNotificationPreferences();
  const updatePrefs = useUpdateVendorNotificationPreferences();
  const [pendingKey, setPendingKey] = useState<string | null>(null);

  const toggle = async (key: keyof VendorNotificationPreferences) => {
    if (!prefs.data) return;
    setPendingKey(key);
    try {
      await updatePrefs.mutateAsync({ ...prefs.data, [key]: !prefs.data[key] });
    } finally {
      setPendingKey(null);
    }
  };

  return (
    <section aria-labelledby="notifications-heading">
      <Card className="space-y-4 p-5 sm:p-6">
        <SectionHeading icon={<Bell size={15} strokeWidth={1.75} />} title="Notification preferences" />
        {prefs.isLoading && <CardSkeleton className="border-none p-0" />}
        {prefs.isError && <ErrorState description="Could not load notification preferences." onRetry={() => prefs.refetch()} />}
        {prefs.data && (
          <div className="divide-y divide-line">
            {NOTIFICATION_TOGGLES.map(({ key, label, description }) => (
              <div key={key} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{label}</p>
                  <p className="mt-0.5 text-xs text-ink-soft">{description}</p>
                </div>
                <ToggleSwitch checked={prefs.data[key]} onChange={() => toggle(key)} disabled={pendingKey === key} />
              </div>
            ))}
          </div>
        )}
        {updatePrefs.isError && (
          <p className="text-xs" style={{ color: "var(--bad)" }} role="alert">
            Could not save that change. Try again.
          </p>
        )}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 4. Availability — reuses the same profile + mutation the existing
// /vendor/service-area page uses, with an added error-state branch.
// -----------------------------------------------------------------------------

function AvailabilitySection() {
  const profile = useVendorProfile();
  const updateAvailability = useUpdateVendorAvailability();

  return (
    <section aria-labelledby="availability-heading">
      <Card className="space-y-4 p-5 sm:p-6">
        <SectionHeading icon={<Power size={15} strokeWidth={1.75} />} title="Availability" />
        {profile.isLoading && <CardSkeleton className="border-none p-0" />}
        {profile.isError && <ErrorState description="Could not load availability." onRetry={() => profile.refetch()} />}
        {profile.data && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-sm font-medium text-ink">
                  {profile.data.availability ? "Available for new jobs" : "Not accepting new jobs"}
                </p>
                <p className="mt-0.5 max-w-md text-xs text-ink-soft">
                  Turning this off removes you from automatic job matching — you won&apos;t be assigned new
                  survey jobs in your service area until you turn it back on.
                </p>
              </div>
              <Button
                type="button"
                variant={profile.data.availability ? "secondary" : "primary"}
                onClick={() => updateAvailability.mutate(!profile.data!.availability)}
                disabled={updateAvailability.isPending}
              >
                {updateAvailability.isPending
                  ? "Updating…"
                  : profile.data.availability
                    ? "Go unavailable"
                    : "Go available"}
              </Button>
            </div>
            {updateAvailability.isError && (
              <p className="text-xs" style={{ color: "var(--bad)" }} role="alert">
                Could not update availability. Try again.
              </p>
            )}
            {updateAvailability.isSuccess && !updateAvailability.isPending && (
              <p className="flex items-center gap-1 text-xs" style={{ color: "var(--good)" }}>
                <Check size={13} strokeWidth={1.75} aria-hidden="true" />
                Updated
              </p>
            )}
          </>
        )}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 5. Service Area — read-only, admin-managed.
// -----------------------------------------------------------------------------

function ServiceAreaSection() {
  const profile = useVendorProfile();
  return (
    <section aria-labelledby="service-area-heading">
      <Card className="space-y-4 p-5 sm:p-6">
        <SectionHeading icon={<MapPin size={15} strokeWidth={1.75} />} title="Service area" />
        {profile.isLoading && <CardSkeleton className="border-none p-0" />}
        {profile.isError && <ErrorState description="Could not load service area." onRetry={() => profile.refetch()} />}
        {profile.data && (
          <>
            <ReadOnlyField label="Region" value={profile.data.serviceArea.region} />
            <div>
              <p className="mb-1.5 text-xs font-medium text-ink-faint">Districts</p>
              <div className="flex flex-wrap gap-1.5">
                {profile.data.serviceArea.districts.map((d) => (
                  <span key={d} className="rounded-[3px] bg-surface-2 px-1.5 py-0.5 text-xs text-ink-soft">
                    {d}
                  </span>
                ))}
              </div>
            </div>
            <p className="text-xs text-ink-soft">
              Service areas are managed by the administrator. Contact support if your service area needs
              to be updated.
            </p>
          </>
        )}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 6. Payout Settings — read-only, already masked server-side.
// -----------------------------------------------------------------------------

function PayoutSettingsSection() {
  const profile = useVendorProfile();
  return (
    <section aria-labelledby="payout-heading">
      <Card className="space-y-4 p-5 sm:p-6">
        <SectionHeading icon={<Wallet size={15} strokeWidth={1.75} />} title="Payout settings" />
        {profile.isLoading && <CardSkeleton className="border-none p-0" />}
        {profile.isError && <ErrorState description="Could not load payout settings." onRetry={() => profile.refetch()} />}
        {profile.data && (
          <>
            <div className="flex items-center gap-3">
              <Wallet size={18} strokeWidth={1.75} className="text-teal" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">{profile.data.payoutMethod.type}</p>
                <p className="font-mono tabular text-sm text-ink-soft">{profile.data.payoutMethod.maskedAccount}</p>
              </div>
            </div>
            <p className="text-xs text-ink-soft">
              Payout method is managed by the administrator. Contact support if it needs to change.
            </p>
          </>
        )}
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------
// 7. Appearance — client-only, applies immediately, no submit button.
// -----------------------------------------------------------------------------

const THEME_OPTIONS: { value: ThemePreference; label: string; icon: React.ReactNode }[] = [
  { value: "system", label: "System", icon: <Monitor size={15} strokeWidth={1.75} /> },
  { value: "light", label: "Light", icon: <Sun size={15} strokeWidth={1.75} /> },
  { value: "dark", label: "Dark", icon: <Moon size={15} strokeWidth={1.75} /> },
];

function AppearanceSection() {
  const theme = useThemePreference();

  return (
    <section aria-labelledby="appearance-heading">
      <Card className="space-y-4 p-5 sm:p-6">
        <SectionHeading icon={<Sun size={15} strokeWidth={1.75} />} title="Appearance" />
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Theme">
          {THEME_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={theme === opt.value}
              onClick={() => setTheme(opt.value)}
              className="flex items-center gap-1.5 rounded-[var(--radius-app)] border px-3 py-2 text-sm"
              style={
                theme === opt.value
                  ? { borderColor: "var(--blue)", color: "var(--blue)", background: "var(--surface-2)" }
                  : { borderColor: "var(--line)", color: "var(--ink-soft)" }
              }
            >
              {opt.icon}
              {opt.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-ink-soft">
          Saved to this browser. Language and date-format preferences aren&apos;t configurable yet — this app&apos;s
          language switcher is currently customer-portal only, and there&apos;s no date-format setting anywhere in
          the product today.
        </p>
      </Card>
    </section>
  );
}

// -----------------------------------------------------------------------------

export function VendorSettingsClient() {
  return (
    <div className="flex flex-col gap-5">
      <AccountInformationSection />
      <PasswordSection />
      <NotificationPreferencesSection />
      <AvailabilitySection />
      <ServiceAreaSection />
      <PayoutSettingsSection />
      <AppearanceSection />
    </div>
  );
}
