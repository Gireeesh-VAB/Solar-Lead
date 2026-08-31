import { afterEach, describe, expect, it, vi } from "vitest";
import { completeCheck, createCheck, listVendorJobs } from "@/lib/api/client";
import { BOUNDARY_REQ, PANORAMA_REQ, SHADING_REQ, USN_REQ } from "@/lib/fixtures/vendor";

// CHECK_VERDICT_POOL in client.ts is
//   [SUITABLE, SUITABLE, SUITABLE_SUBJECT_TO_SURVEY, CONDITIONAL, INSUFFICIENT_DATA, NOT_SUITABLE]
// generateCheckAssessment() picks an index via Math.floor(Math.random() * 6),
// so mocking Math.random pins the verdict deterministically.
const RANDOM_FOR_SUITABLE = 0.05; // index 0 -> SUITABLE
const RANDOM_FOR_SURVEY = 0.4; // index 2 -> SUITABLE_SUBJECT_TO_SURVEY
const RANDOM_FOR_NOT_SUITABLE = 0.9; // index 5 -> NOT_SUITABLE

async function jobForCheck(checkId: string) {
  const jobs = await listVendorJobs();
  return jobs.find((j) => j.siteId === checkId);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("completeCheck vendor job handoff", () => {
  it("creates a vendor job when the verdict is SUITABLE_SUBJECT_TO_SURVEY", async () => {
    vi.spyOn(Math, "random").mockReturnValue(RANDOM_FOR_SURVEY);
    const check = await createCheck({ address: "Survey St", lat: 17.4, lng: 78.4, siteType: "ROOFTOP_RESIDENTIAL" });

    const completed = await completeCheck(check.id);

    expect(completed.latestAssessment?.verdict).toBe("SUITABLE_SUBJECT_TO_SURVEY");
    const job = await jobForCheck(check.id);
    expect(job).toBeDefined();
    expect(job?.status).toBe("queued");
    expect(job?.payoutInr).toBeGreaterThan(0);
    expect(job?.deadline).toBeTruthy();
  });

  it("does not create a vendor job for a SUITABLE verdict", async () => {
    vi.spyOn(Math, "random").mockReturnValue(RANDOM_FOR_SUITABLE);
    const check = await createCheck({ address: "Suitable St", lat: 17.4, lng: 78.4, siteType: "ROOFTOP_RESIDENTIAL" });

    const completed = await completeCheck(check.id);

    expect(completed.latestAssessment?.verdict).toBe("SUITABLE");
    expect(await jobForCheck(check.id)).toBeUndefined();
  });

  it("does not create a vendor job for a NOT_SUITABLE verdict", async () => {
    vi.spyOn(Math, "random").mockReturnValue(RANDOM_FOR_NOT_SUITABLE);
    const check = await createCheck({ address: "Not Suitable St", lat: 17.4, lng: 78.4, siteType: "ROOFTOP_RESIDENTIAL" });

    const completed = await completeCheck(check.id);

    expect(completed.latestAssessment?.verdict).toBe("NOT_SUITABLE");
    expect(await jobForCheck(check.id)).toBeUndefined();
  });

  it("derives job requirements from the site type", async () => {
    vi.spyOn(Math, "random").mockReturnValue(RANDOM_FOR_SURVEY);

    const residential = await createCheck({ address: "Residential Rd", lat: 17.4, lng: 78.4, siteType: "ROOFTOP_RESIDENTIAL" });
    await completeCheck(residential.id);
    const residentialJob = await jobForCheck(residential.id);
    expect(residentialJob?.requirements).toEqual([BOUNDARY_REQ, PANORAMA_REQ, USN_REQ, SHADING_REQ]);

    const floating = await createCheck({ address: "Reservoir Rd", lat: 16.5, lng: 80.6, siteType: "FLOATING" });
    await completeCheck(floating.id);
    const floatingJob = await jobForCheck(floating.id);
    expect(floatingJob?.requirements).toEqual([BOUNDARY_REQ, PANORAMA_REQ, SHADING_REQ]);
  });
});
