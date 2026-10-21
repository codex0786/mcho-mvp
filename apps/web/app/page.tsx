import ObservatoryDashboard from "../components/ObservatoryDashboard";

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <div><div className="eyebrow">EVIDENCE-FIRST REGIONAL MONITORING</div><h1>MENA Conflict &amp; Humanitarian Observatory</h1></div>
        <nav className="header-actions" aria-label="Site">
          <span className="status">Live satellite feed · NASA FIRMS, unverified</span>
          <a className="text-link" href="/about">About the data →</a>
          <a className="text-link" href="/demo">Design preview (sample data) →</a>
        </nav>
      </header>
      <section className="notice" role="status"><strong>Data status:</strong> Satellite heat detections update about hourly from NASA FIRMS and are analysed automatically. They are unverified observations: a detection can be conflict-related fire, crop burning, wildfire or a gas flare. No human-verified events are published yet.</section>
      <ObservatoryDashboard />
      <footer>Demonstration · Satellite data: NASA FIRMS (VIIRS) · Borders: Natural Earth · Basemap: OpenFreeMap / OpenStreetMap contributors · Not for tactical or targeting decisions.</footer>
    </main>
  );
}
