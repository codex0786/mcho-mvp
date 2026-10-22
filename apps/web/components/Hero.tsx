"use client";

import { AnimatedNumber, Reveal } from "./Motion";

export type HeroStats = {
  heat: number | null; heatNew: number | null; hours: number;
  deaths: number | null; events: number | null; months: string | null;
  destroyed: number | null; damageLabel: string | null;
  hormuzChange: number | null;
};

function Stat({ value, label, detail, tone, suffix = "" }: { value: number | null; label: string; detail: string; tone: string; suffix?: string }) {
  return (
    <div className={`hero-stat tone-${tone}`}>
      <div className="hero-stat-value">
        {value === null ? <span className="stat-skeleton" aria-label="Loading" /> : <><AnimatedNumber value={value} />{suffix}</>}
      </div>
      <div className="hero-stat-label">{label}</div>
      <div className="hero-stat-detail">{detail}</div>
    </div>
  );
}

export default function Hero({ stats, place }: { stats: HeroStats; place: string }) {
  const change = stats.hormuzChange;
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-backdrop" aria-hidden="true">
        <div className="hero-aurora" />
        <svg className="hero-globe" viewBox="0 0 600 600">
          <defs>
            <radialGradient id="globe-fill" cx="40%" cy="35%" r="70%">
              <stop offset="0%" stopColor="#1d4f7a" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#050b14" stopOpacity="0" />
            </radialGradient>
          </defs>
          <circle cx="300" cy="300" r="250" fill="url(#globe-fill)" />
          {[60, 110, 160, 210, 250].map((r) => <ellipse key={`lat${r}`} cx="300" cy="300" rx="250" ry={r} className="globe-line" />)}
          {[40, 100, 160, 220, 250].map((r) => <ellipse key={`lon${r}`} cx="300" cy="300" rx={r} ry="250" className="globe-line" />)}
          <g className="globe-orbit"><circle cx="300" cy="50" r="5" className="globe-sat" /></g>
          {[[355, 250], [330, 330], [400, 290], [280, 300], [420, 340]].map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r="4" className="globe-ping" style={{ animationDelay: `${i * 0.7}s` }} />
          ))}
        </svg>
        <div className="hero-scan" />
      </div>
      <div className="hero-content">
        <Reveal><div className="hero-eyebrow"><span className="live-dot" aria-hidden="true" />Evidence-first regional monitoring</div></Reveal>
        <Reveal delay={80}><h1 id="hero-title">See what satellites and verified sources show across the Middle East &amp; North Africa</h1></Reveal>
        <Reveal delay={160}>
          <p className="hero-lede">
            Fresh NASA heat detections every hour, cross-checked against UCDP&apos;s verified record of deadly violence, UN satellite damage
            assessments and IMF shipping data. Every figure links back to its source.
          </p>
        </Reveal>
        <Reveal delay={240}>
          <div className="hero-actions">
            <a className="btn btn-primary" href="#map">Explore the live map</a>
            <a className="btn btn-ghost" href="/about">How it works</a>
          </div>
        </Reveal>
        <Reveal delay={320}>
          <div className="hero-stats" aria-label={`Headline figures, ${place}`}>
            <Stat value={stats.heat} tone="heat" label={`Satellite heat detections, last ${stats.hours} h`}
              detail={stats.heatNew === null ? "NASA FIRMS · unverified" : `${stats.heatNew.toLocaleString("en-GB")} at new locations · unverified`} />
            <Stat value={stats.deaths} tone="violence" label="Deaths in verified violent events"
              detail={stats.events === null ? "UCDP · preliminary" : `${stats.events.toLocaleString("en-GB")} events · ${stats.months ?? ""} · UCDP`} />
            <Stat value={stats.destroyed} tone="damage" label="Structures destroyed (UN assessed)"
              detail={stats.damageLabel ?? "UNOSAT satellite assessments"} />
            <Stat value={change === null ? null : Math.abs(change)} suffix="%" tone="shipping"
              label={change === null ? "Strait of Hormuz traffic vs last year" : `Strait of Hormuz traffic ${change < 0 ? "down" : "up"} vs last year`}
              detail="Ships per day, 7-day average · IMF PortWatch" />
          </div>
        </Reveal>
        <p className="hero-place">Figures for {place}. Heat signatures are leads, not confirmed events.</p>
      </div>
    </section>
  );
}
