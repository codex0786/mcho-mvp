import type { Metadata } from "next";
import "./styles.css";

export const metadata: Metadata = {
  title: "MCHO | MENA Conflict & Humanitarian Observatory",
  description: "Evidence-first regional monitoring and humanitarian context.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
