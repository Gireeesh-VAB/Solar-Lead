// -----------------------------------------------------------------------------
// Server Component data fetching ONLY — do not import this from a "use
// client" component. Server Components render before any browser JS runs,
// so they can't read localStorage (lib/auth/session.ts); this reads the
// bearer token from the `sf_token` cookie that session.ts mirrors there
// instead (see setStoredSession/clearStoredSession).
//
// Deliberately separate from lib/api/fetchClient.ts's apiFetch(), which is
// browser-only (localStorage) and used by every hook in lib/query/hooks.ts.
// -----------------------------------------------------------------------------

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { Agent } from "undici";
import type { AdminVendorSummary, Site, VendorJob, VendorProfile } from "@/lib/types";
import type { CustomerProfile } from "@/lib/fixtures/customer";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Local dev serves the backend over HTTPS with a self-signed cert
// (../certs/dev-cert.pem, same file uvicorn/next dev are both launched
// with). Node's fetch (undici) rejects that by default with
// DEPTH_ZERO_SELF_SIGNED_CERT — every server-side fetch in this file was
// silently failing on that, not on auth, and every caller's `.catch(() =>
// null)` turned it into a misleading "not found" page. Trusting exactly
// this repo's own dev cert as an extra CA (scoped to this one dispatcher,
// not process-wide) fixes the SSR fetch without weakening TLS verification
// for anything else. Missing/unreadable in a deployment that doesn't ship
// this file (e.g. production, a real CA-signed backend) — falls back to
// undici's default dispatcher, which is exactly what you want there.
function buildDispatcher(): Agent | undefined {
  try {
    const certPath = join(process.cwd(), "..", "certs", "dev-cert.pem");
    const ca = readFileSync(certPath);
    return new Agent({ connect: { ca } });
  } catch {
    return undefined;
  }
}

const devDispatcher = process.env.NODE_ENV === "production" ? undefined : buildDispatcher();

// Thrown instead of a generic Error on a 401/403 so callers can tell "you're
// not signed in (any more)" apart from "this really doesn't exist" — see
// orRedirectToLogin() below. Without this distinction, a stale/expired
// sf_token cookie makes every page in this file collapse to a misleading
// notFound(), which reads as "this job/vendor/site was deleted" when the
// real problem is just the session.
export class UnauthorizedError extends Error {}

async function serverApiFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies();
  const token = cookieStore.get("sf_token")?.value;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}${path}`, {
    headers,
    cache: "no-store",
    // @ts-expect-error -- undici-only fetch option, not in the standard lib.dom fetch types
    dispatcher: devDispatcher,
  });
  if (response.status === 401 || response.status === 403) {
    throw new UnauthorizedError(`Request to ${path} failed with status ${response.status}`);
  }
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

// Wrap a serverFetch call with this instead of `.catch(() => null)` on any
// page where a real 401/403 should send the visitor back to sign in rather
// than render a "not found" page. Only UnauthorizedError triggers the
// redirect — every other failure (a genuinely missing id, a network blip)
// still falls through to the caller's own null/notFound() handling.
export async function orRedirectToLogin<T>(promise: Promise<T>, loginPath = "/login"): Promise<T | null> {
  try {
    return await promise;
  } catch (err) {
    if (err instanceof UnauthorizedError) redirect(loginPath);
    return null;
  }
}

export const getSiteServer = (siteId: string): Promise<Site> => serverApiFetch<Site>(`/app/sites/${siteId}`);

export const getVendorJobServer = (jobId: string): Promise<VendorJob> =>
  serverApiFetch<VendorJob>(`/app/vendor/jobs/${jobId}`);

export const getVendorProfileServer = (): Promise<VendorProfile> => serverApiFetch<VendorProfile>("/app/vendor/profile");

export const getAdminVendorServer = (id: string): Promise<AdminVendorSummary> =>
  serverApiFetch<AdminVendorSummary>(`/app/admin/vendors/${id}`);

export const getCustomerProfileServer = (): Promise<CustomerProfile> =>
  serverApiFetch<CustomerProfile>("/app/customer/profile");

export const listChecksServer = (): Promise<Site[]> => serverApiFetch<Site[]>("/app/checks");

export const getCheckServer = (checkId: string): Promise<Site> => serverApiFetch<Site>(`/app/checks/${checkId}`);
