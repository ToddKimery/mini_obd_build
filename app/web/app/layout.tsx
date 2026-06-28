import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import Link from "next/link";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Mini OBD",
  description: "R56 N14 OBD Data Logger",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} bg-slate-950 text-slate-100 min-h-screen`}>
        <header className="sticky top-0 z-10 bg-slate-900/80 backdrop-blur border-b border-slate-800 px-4 py-3 flex items-center justify-between">
          <Link href="/" className="font-semibold text-slate-100 tracking-tight">
            Mini OBD &nbsp;
            <span className="text-slate-500 font-normal text-sm">R56 N14</span>
          </Link>
          <nav className="flex gap-4 text-sm">
            <Link href="/" className="text-slate-400 hover:text-slate-100 transition-colors">
              Live
            </Link>
            <Link href="/sessions" className="text-slate-400 hover:text-slate-100 transition-colors">
              Sessions
            </Link>
          </nav>
        </header>
        <main className="px-4 py-5 max-w-2xl mx-auto">{children}</main>
      </body>
    </html>
  );
}
