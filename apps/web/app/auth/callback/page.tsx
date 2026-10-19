"use client";

import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function AuthCallbackPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/analyst");
  }, [router]);

  return (
    <main className="shell workspace-shell">
      <section className="workspace-card callback-card" aria-live="polite">
        <div className="eyebrow">MCHO AUTHENTICATION</div>
        <h1>Secure sign-in</h1>
        <p className="muted">The authorization callback is handled by the server. Returning to the analyst workspace…</p>
        <Link className="text-link" href="/analyst">Return to analyst workspace</Link>
      </section>
    </main>
  );
}
