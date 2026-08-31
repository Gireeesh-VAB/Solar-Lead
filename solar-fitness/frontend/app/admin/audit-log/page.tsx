import type { Metadata } from "next";
import { PageHeader } from "@/components/ui/Primitives";
import { AuditLogClient } from "./AuditLogClient";

export const metadata: Metadata = {
  title: "Audit log",
  description: "Read-only, append-only log of privileged actions taken across the platform.",
};

export default function AdminAuditLogPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Audit log" description="Append-only record of privileged platform actions. Read-only." />
      <AuditLogClient />
    </div>
  );
}
