import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Instagram Content Factory",
  description: "Content pipeline & scheduling dashboard",
};

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/accounts", label: "Accounts" },
  { href: "/masters", label: "Masters" },
  { href: "/inventory", label: "Inventory" },
  { href: "/calendar", label: "Calendar" },
  { href: "/queue", label: "Queue" },
  { href: "/errors", label: "Errors" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <div className="mx-auto max-w-6xl px-6 py-8">
          <header className="mb-8 flex items-center justify-between">
            <h1 className="text-xl font-semibold tracking-tight">Instagram Content Factory</h1>
            <nav className="flex gap-4 text-sm text-gray-400">
              {NAV.map((item) => (
                <a key={item.href} href={item.href} className="hover:text-white">
                  {item.label}
                </a>
              ))}
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}
