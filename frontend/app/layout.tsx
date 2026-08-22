import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Company Intelligence",
  description: "AI agent for company email intelligence with human-in-the-loop approval",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="mx-auto flex min-h-screen max-w-[1400px] flex-col gap-4 p-4">
          <header className="brutal-card flex items-center justify-between px-4 py-3">
            <Link href="/" className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center border-2 border-ink bg-accent text-lg font-black shadow-brutal-sm">
                CI
              </span>
              <span>
                <span className="block text-base font-black leading-tight tracking-tight">
                  COMPANY INTEL
                </span>
                <span className="block text-[10px] font-bold uppercase tracking-widest text-ink/60">
                  AI Agent
                </span>
              </span>
            </Link>
            <nav className="flex items-center gap-3">
              <Link href="/" className="brutal-btn bg-paper hover:bg-accent">
                Chat
              </Link>
              <Link href="/dashboard" className="brutal-btn bg-paper hover:bg-accent">
                Dashboard
              </Link>
            </nav>
          </header>
          <main className="flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
