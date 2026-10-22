"use client";

import { useEffect, useState } from "react";

const LINKS = [
  { href: "/#map", id: "map", label: "Live map" },
  { href: "/#violence", id: "violence", label: "Verified violence" },
  { href: "/#damage", id: "damage", label: "Damage" },
  { href: "/#shipping", id: "shipping", label: "Shipping" },
];

export default function SiteNav({ page = "home" }: { page?: "home" | "about" }) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    if (page !== "home" || typeof IntersectionObserver === "undefined") return () => window.removeEventListener("scroll", onScroll);
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setActive(visible.target.id);
    }, { rootMargin: "-35% 0px -55% 0px", threshold: [0, 0.25, 0.5] });
    LINKS.forEach((l) => { const el = document.getElementById(l.id); if (el) observer.observe(el); });
    return () => { window.removeEventListener("scroll", onScroll); observer.disconnect(); };
  }, [page]);

  return (
    <header className={`site-nav${scrolled ? " is-scrolled" : ""}`}>
      <div className="site-nav-inner">
        <a className="brand" href="/" aria-label="MCHO home">
          <span className="brand-mark" aria-hidden="true"><span /></span>
          <span className="brand-text"><strong>MCHO</strong><small>MENA Observatory</small></span>
        </a>
        <button type="button" className="nav-toggle" aria-expanded={open} aria-controls="site-links" onClick={() => setOpen((v) => !v)}>
          <span className="sr-only">Menu</span><span aria-hidden="true" />
        </button>
        <nav id="site-links" className={`nav-links${open ? " is-open" : ""}`} aria-label="Site">
          {LINKS.map((l) => (
            <a key={l.id} href={l.href} className={active === l.id ? "is-active" : ""} onClick={() => setOpen(false)}>{l.label}</a>
          ))}
          <a href="/about" className={page === "about" ? "is-active" : ""}>About the data</a>
          <span className="live-pill" title="Satellite data updates about hourly"><i aria-hidden="true" />Live</span>
        </nav>
      </div>
    </header>
  );
}
