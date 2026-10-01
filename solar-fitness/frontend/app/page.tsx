import Navigation from "@/components/landing/Navigation";
import HeroSection from "@/components/landing/HeroSection";
import CTASection from "@/components/landing/CTASection";
import VendorsSection from "@/components/landing/VendorsSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import FAQSection from "@/components/landing/FAQSection";
import Footer from "@/components/landing/Footer";

export default function RootPage() {
  return (
    <main className="min-h-screen bg-white">
      <Navigation />
      <HeroSection />
      <CTASection />
      <VendorsSection />
      <FeaturesSection />
      <FAQSection />
      <Footer />
    </main>
  );
}
