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

import { cookies } from "next/headers";
import type { AdminVendorSummary, Site, Tenant, VendorJob, VendorProfile } from "@/lib/types";
import type { CustomerProfile } from "@/lib/fixtures/customer";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function serverApiFetch<T>(path: string): Promise<T> {
  const cookieStore = await cookies();
  const token = cookieStore.get("sf_token")?.value;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;

  const response = await fetch(`${BASE_URL}${path}`, { headers, cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request to ${path} failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

export const getSiteServer = (siteId: string): Promise<Site> => serverApiFetch<Site>(`/app/sites/${siteId}`);

export const getVendorJobServer = (jobId: string): Promise<VendorJob> =>
  serverApiFetch<VendorJob>(`/app/vendor/jobs/${jobId}`);

export const getVendorProfileServer = (): Promise<VendorProfile> => serverApiFetch<VendorProfile>("/app/vendor/profile");

export const getAdminVendorServer = (id: string): Promise<AdminVendorSummary> =>
  serverApiFetch<AdminVendorSummary>(`/app/admin/vendors/${id}`);

export const getTenantServer = (id: string): Promise<Tenant> => serverApiFetch<Tenant>(`/app/admin/customers/${id}`);

export const getCustomerProfileServer = (): Promise<CustomerProfile> =>
  serverApiFetch<CustomerProfile>("/app/customer/profile");

export const listChecksServer = (): Promise<Site[]> => serverApiFetch<Site[]>("/app/checks");

export const getCheckServer = (checkId: string): Promise<Site> => serverApiFetch<Site>(`/app/checks/${checkId}`);
