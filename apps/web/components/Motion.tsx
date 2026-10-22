"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Fades and lifts its content into view the first time it scrolls on screen. */
export function Reveal({ children, delay = 0, className = "" }: { children: ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || prefersReducedMotion() || typeof IntersectionObserver === "undefined") { setShown(true); return; }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setShown(true); observer.disconnect(); }
    }, { rootMargin: "0px 0px -8% 0px" });
    observer.observe(node);
    // Content is never left hidden if the observer does not fire (e.g. background tabs, print).
    const fallback = setTimeout(() => setShown(true), 2500);
    return () => { observer.disconnect(); clearTimeout(fallback); };
  }, []);
  return (
    <div ref={ref} className={`reveal${shown ? " is-visible" : ""} ${className}`} style={{ transitionDelay: `${delay}ms` }}>
      {children}
    </div>
  );
}

/** Counts up to a value once; shows the final value immediately when motion is reduced. */
export function AnimatedNumber({ value, duration = 1200 }: { value: number | null; duration?: number }) {
  const [shown, setShown] = useState<number | null>(value === null ? null : 0);
  const from = useRef(0);
  useEffect(() => {
    if (value === null) { setShown(null); return; }
    if (prefersReducedMotion()) { setShown(value); from.current = value; return; }
    const start = performance.now();
    const origin = from.current;
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(Math.round(origin + (value - origin) * eased));
      if (t < 1) frame = requestAnimationFrame(step); else from.current = value;
    };
    frame = requestAnimationFrame(step);
    // Browsers pause animation frames in background tabs; always land on the real value.
    const settle = setTimeout(() => { cancelAnimationFrame(frame); setShown(value); from.current = value; }, duration + 150);
    return () => { cancelAnimationFrame(frame); clearTimeout(settle); };
  }, [value, duration]);
  return <>{shown === null ? "—" : shown.toLocaleString("en-GB")}</>;
}
