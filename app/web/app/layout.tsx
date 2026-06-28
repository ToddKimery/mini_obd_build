import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { SettingsProvider } from "@/lib/settings";
import { NavBar } from "@/components/NavBar";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mini OBD",
  description: "R56 N14 OBD Data Logger",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-100 min-h-screen`}>
        <SettingsProvider>
          <NavBar />
          <main className="px-4 py-5 max-w-2xl mx-auto">{children}</main>
        </SettingsProvider>
      </body>
    </html>
  );
}
