import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { SettingsProvider } from "@/lib/settings";
import { NavBar } from "@/components/NavBar";
import { RegisterSW } from "@/components/RegisterSW";
import { SplashScreen } from "@/components/SplashScreen";

const inter = Inter({ subsets: ["latin"] });

export const viewport: Viewport = {
  themeColor: "#10b981",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "Mini OBD",
  description: "R56 N14 OBD Data Logger",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    title: "Mini OBD",
    statusBarStyle: "black-translucent",
  },
  icons: {
    apple: [{ url: "/icons/launchericon-192x192.png", sizes: "192x192" }],
    icon: "/icons/launchericon-192x192.png",
  },
  other: {
    // Next.js generates mobile-web-app-capable; iOS also needs the apple- prefixed version
    "apple-mobile-web-app-capable": "yes",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-100 min-h-screen`}>
        <SplashScreen />
        <RegisterSW />
        <SettingsProvider>
          <NavBar />
          <main className="px-4 py-5 max-w-2xl mx-auto">{children}</main>
        </SettingsProvider>
      </body>
    </html>
  );
}
