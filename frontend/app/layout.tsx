import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "katex/dist/katex.min.css";
import "./globals.css";
import { TradingProvider } from "@/hooks/useTradingContext";
import { AuthProvider } from "@/hooks/useAuthContext";
import SmoothScroll from "@/components/SmoothScroll";
import CustomCursor from "@/components/ui/CustomCursor";
import TradingNav from "@/components/ui/TradingNav";

export const metadata: Metadata = {
  title: "Sonnetrade-AI",
  description: "Premium AI Auto Signal Trading",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans antialiased">
        <CustomCursor />
        <AuthProvider>
          <TradingProvider>
            <SmoothScroll>
              <TradingNav />
              {children}
            </SmoothScroll>
          </TradingProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
