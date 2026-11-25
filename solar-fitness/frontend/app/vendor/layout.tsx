import { VendorSidebar } from "@/components/vendor/VendorSidebar";
import { VendorHeader } from "@/components/vendor/VendorHeader";
import { AuthGuard } from "@/components/auth/AuthGuard";

export default function VendorLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard role="vendor">
      <div className="flex min-h-screen w-full">
        <VendorSidebar />
        <div className="flex min-h-screen flex-1 flex-col">
          <VendorHeader />
          <main className="flex-1 overflow-x-hidden px-4 py-6 md:px-6">{children}</main>
        </div>
      </div>
    </AuthGuard>
  );
}
