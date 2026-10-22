import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./styles.css";
import "./theme.css";

// Self-hosted at build time by Next.js, so no request goes to Google from the browser.
const inter = Inter({ subsets: ["latin"], variable: "--font-body", display: "swap" });
const grotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-display", display: "swap" });

export const metadata: Metadata = {
  title: "MCHO | MENA Conflict & Humanitarian Observatory",
  description: "Evidence-first regional monitoring and humanitarian context.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en" className={`${inter.variable} ${grotesk.variable}`}><body>{children}</body></html>;
}
