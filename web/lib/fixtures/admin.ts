import type { AdminVendorSummary, AuditLogEntry, PlatformHealthMetric } from "@/lib/types";

// Hand-written super-admin fixtures. Billing contacts use fake example.com
// domains — never the real signed-in user's email.

function daysAgo(days: number): string {
  return new Date(Date.now() - days * 86400000).toISOString();
}

export const MOCK_ADMIN_VENDORS: AdminVendorSummary[] = [
  { id: "VEN-001", name: "Sunline Survey Co.", verificationStatus: "verified", accuracyScore: 96, slaCompliancePct: 98, activeJobs: 6, totalJobsCompleted: 412, serviceArea: "Rangareddy, Hyderabad", joinedAt: daysAgo(520), payoutMethod: "UPI" },
  { id: "VEN-002", name: "Deccan Field Surveyors", verificationStatus: "verified", accuracyScore: 91, slaCompliancePct: 94, activeJobs: 4, totalJobsCompleted: 288, serviceArea: "Guntur, Krishna", joinedAt: daysAgo(410), payoutMethod: "Bank transfer" },
  { id: "VEN-003", name: "Rooftop Precision Surveys", verificationStatus: "verified", accuracyScore: 88, slaCompliancePct: 90, activeJobs: 9, totalJobsCompleted: 501, serviceArea: "Ahmedabad, Surat", joinedAt: daysAgo(600), payoutMethod: "UPI" },
  { id: "VEN-004", name: "Coastal Solar Assessors", verificationStatus: "pending", accuracyScore: 0, slaCompliancePct: 0, activeJobs: 0, totalJobsCompleted: 0, serviceArea: "Visakhapatnam", joinedAt: daysAgo(3), payoutMethod: "UPI" },
  { id: "VEN-005", name: "Karnataka Grid Surveyors", verificationStatus: "verified", accuracyScore: 93, slaCompliancePct: 96, activeJobs: 5, totalJobsCompleted: 356, serviceArea: "Bengaluru Rural, Mysuru", joinedAt: daysAgo(480), payoutMethod: "Bank transfer" },
  { id: "VEN-006", name: "QuickScan Rooftop Services", verificationStatus: "pending", accuracyScore: 0, slaCompliancePct: 0, activeJobs: 0, totalJobsCompleted: 0, serviceArea: "Pune", joinedAt: daysAgo(1), payoutMethod: "UPI" },
  { id: "VEN-007", name: "Vishnu Structural Surveys", verificationStatus: "rejected", accuracyScore: 61, slaCompliancePct: 58, activeJobs: 0, totalJobsCompleted: 22, serviceArea: "Warangal", joinedAt: daysAgo(200), payoutMethod: "UPI" },
  { id: "VEN-008", name: "Godavari Delta Field Ops", verificationStatus: "verified", accuracyScore: 89, slaCompliancePct: 92, activeJobs: 3, totalJobsCompleted: 174, serviceArea: "East Godavari", joinedAt: daysAgo(340), payoutMethod: "Bank transfer" },
  { id: "VEN-009", name: "Metro Rooftop Auditors", verificationStatus: "suspended", accuracyScore: 74, slaCompliancePct: 68, activeJobs: 0, totalJobsCompleted: 96, serviceArea: "Mumbai Metropolitan", joinedAt: daysAgo(390), payoutMethod: "UPI" },
  { id: "VEN-010", name: "Bharath Floating Solar Surveys", verificationStatus: "verified", accuracyScore: 90, slaCompliancePct: 93, activeJobs: 2, totalJobsCompleted: 68, serviceArea: "Krishna Reservoirs", joinedAt: daysAgo(150), payoutMethod: "UPI" },
  { id: "VEN-011", name: "Nizam Structural Inspections", verificationStatus: "pending", accuracyScore: 0, slaCompliancePct: 0, activeJobs: 0, totalJobsCompleted: 0, serviceArea: "Hyderabad Old City", joinedAt: daysAgo(2), payoutMethod: "Bank transfer" },
  { id: "VEN-012", name: "Chennai Coastal Surveyors", verificationStatus: "verified", accuracyScore: 87, slaCompliancePct: 89, activeJobs: 7, totalJobsCompleted: 233, serviceArea: "Chennai, Kanchipuram", joinedAt: daysAgo(300), payoutMethod: "UPI" },
];

export const MOCK_AUDIT_LOG: AuditLogEntry[] = [
  { id: "AUD-2200", actor: "admin@platform", action: "vendor.verified", target: "VEN-005 · Karnataka Grid Surveyors", timestamp: daysAgo(2), details: "Verification documents reviewed and approved." },
  { id: "AUD-2199", actor: "ml-platform@vabinformatics.com", action: "model.proposed", target: "MDL-2.4.0-rc1 · fitness-core", timestamp: daysAgo(3), details: "New candidate model version submitted for review." },
  { id: "AUD-2198", actor: "admin@platform", action: "calibration.approved", target: "CAL-497 · Gujarat — Ahmedabad", timestamp: daysAgo(4), details: "No adjustment applied — variance within tolerance." },
  { id: "AUD-2197", actor: "calibration-engine", action: "calibration.proposed", target: "CAL-501 · Telangana — Rangareddy", timestamp: daysAgo(5), details: "Usable roof area factor recalibration proposed from field variance." },
  { id: "AUD-2196", actor: "admin@platform", action: "vendor.suspended", target: "VEN-009 · Metro Rooftop Auditors", timestamp: daysAgo(6), details: "SLA compliance fell below 70% threshold for two consecutive months." },
  { id: "AUD-2194", actor: "admin@platform", action: "jurisdiction.published", target: "JUR-TS · Telangana v2026.03", timestamp: daysAgo(10), details: "Published updated constraint pack with revised net-metering ceiling." },
  { id: "AUD-2193", actor: "admin@platform", action: "vendor.rejected", target: "VEN-007 · Vishnu Structural Surveys", timestamp: daysAgo(12), details: "Rejected onboarding — accuracy score below platform minimum." },
  { id: "AUD-2192", actor: "system@fitness-engine", action: "model.approved", target: "MDL-2.3.1 · fitness-core", timestamp: daysAgo(60), details: "Promoted to active production model." },
  { id: "AUD-2189", actor: "admin@platform", action: "config.quota_updated", target: "Google Maps API", timestamp: daysAgo(15), details: "Monthly quota raised from 400,000 to 500,000 calls." },
  { id: "AUD-2188", actor: "admin@platform", action: "config.key_rotated", target: "Vision API key", timestamp: daysAgo(20), details: "API key rotated as part of scheduled security review." },
  { id: "AUD-2186", actor: "admin@platform", action: "vendor.verified", target: "VEN-010 · Bharath Floating Solar Surveys", timestamp: daysAgo(150), details: "Verification documents reviewed and approved." },
  { id: "AUD-2185", actor: "admin@platform", action: "jurisdiction.published", target: "JUR-GJ · Gujarat v2026.01", timestamp: daysAgo(70), details: "Published updated constraint pack for floating solar coverage cap." },
  { id: "AUD-2184", actor: "system@fitness-engine", action: "model.rejected", target: "MDL-2.2.6 · fitness-core", timestamp: daysAgo(95), details: "Rejected — regressed on floating-array capacity estimates." },
  { id: "AUD-2183", actor: "admin@platform", action: "vendor.verified", target: "VEN-008 · Godavari Delta Field Ops", timestamp: daysAgo(340), details: "Verification documents reviewed and approved." },
];

export const MOCK_PLATFORM_HEALTH: PlatformHealthMetric = {
  uptimePct: 99.94,
  incidentsThisMonth: 1,
  quotas: [
    { service: "Google Maps API", used: 462000, limit: 500000, unit: "calls" },
    { service: "Solar API", used: 178500, limit: 250000, unit: "calls" },
    { service: "Vision API", used: 91200, limit: 100000, unit: "calls" },
    { service: "Weather API", used: 38400, limit: 150000, unit: "calls" },
  ],
};
