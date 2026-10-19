import RegionalMap from "../components/RegionalMap";

export default function Home() {
  return (
    <main className="shell">
      <header className="topbar">
        <div><div className="eyebrow">EVIDENCE-FIRST REGIONAL MONITORING</div><h1>MENA Conflict &amp; Humanitarian Observatory</h1></div>
        <div className="header-actions"><span className="status">MVP scaffold · No live feed configured</span><a className="text-link" href="/demo">Interactive prototype →</a><a className="text-link" href="/analyst">Analyst workspace →</a></div>
      </header>
      <section className="notice" role="status"><strong>Data status:</strong> This deployment does not contain live conflict data. Connect authorized sources and complete verification before publishing real events.</section>
      <section className="toolbar" aria-label="Map filters">
        <label>From <input id="from-date" type="date" /></label>
        <label>To <input id="to-date" type="date" /></label>
        <label>Verification <select id="verification"><option value="">All published</option><option value="verified">Verified</option><option value="provisional">Provisional</option><option value="disputed">Disputed</option></select></label>
        <button id="refresh" type="button">Refresh map data</button>
      </section>
      <div className="content-grid">
        <section className="map-card"><div className="section-heading"><h2>Regional map</h2><span>Published, sourced records only</span></div><RegionalMap /></section>
        <aside className="side-card"><h2>Evidence feed</h2><p className="muted">Select a map feature to inspect its evidence. Synthetic records are excluded.</p><div id="event-list" className="event-list"><div className="empty">No published events loaded.</div></div><div className="section-divider"/><h3>Data quality</h3><ul className="quality-list"><li>Source freshness shown by API timestamps</li><li>Missing data is not interpreted as absence of an event</li><li>Attribution and verification are distinct</li><li>Satellite candidates require human review</li></ul></aside>
      </div>
      <footer>Prototype only · Not for tactical or targeting decisions · Source access and publication policy must be configured by the deploying organization.</footer>
    </main>
  );
}
