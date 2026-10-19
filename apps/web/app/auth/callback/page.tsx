"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createOidcUserManager, isOidcConfigured, loadRuntimeConfig } from "../../../lib/oidc";

export default function AuthCallbackPage() {
  const router = useRouter();
  const started = useRef(false);
  const [message, setMessage] = useState("Completing secure sign-in…");

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    let active = true;

    async function completeSignIn() {
      try {
        setMessage("Checking identity-provider configuration…");
        const config = await loadRuntimeConfig();
        if (!isOidcConfigured(config)) {
          throw new Error("This deployment has not been configured with an OIDC authority and client ID.");
        }
        const manager = createOidcUserManager(config);
        setMessage("Validating the authorization response…");
        await manager.signinRedirectCallback();
        if (active) {
          router.replace("/analyst");
        }
      } catch (error) {
        if (active) {
          setMessage(error instanceof Error ? error.message : "Sign-in could not be completed.");
        }
      }
    }

    void completeSignIn();
    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="shell workspace-shell">
      <section className="workspace-card callback-card" aria-live="polite">
        <div className="eyebrow">MCHO AUTHENTICATION</div>
        <h1>Secure sign-in</h1>
        <p className="muted">{message}</p>
        <p className="muted">The access token is never displayed on this page.</p>
        <Link className="text-link" href="/analyst">Return to analyst workspace</Link>
      </section>
    </main>
  );
}
