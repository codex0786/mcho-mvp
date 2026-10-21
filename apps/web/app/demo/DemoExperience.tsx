"use client";

import { useMemo, useState } from "react";

type DemoStatus = "review" | "provisional" | "verified";
type DemoRecord = {
  id: string;
  status: DemoStatus;
  title: string;
  type: string;
  place: string;
  when: string;
  summary: string;
  source: string;
  url: string;
  retrieved: string;
  hash: string;
  evidence: string;
  confidence: string;
  rationale: string;
  x: number;
  y: number;
};

const DEMO_RECORDS: DemoRecord[] = [
  {
    id: "e1", status: "review", title: "Illustrative infrastructure report",
    type: "Infrastructure damage", place: "Levant region · illustrative",
    when: "18 Oct 2026, 14:20 UTC (fictional)",
    summary: "A fictional publisher metadata record is awaiting source review. It is not an incident claim and no physical damage is asserted by this interface.",
    source: "Example Publisher A", url: "https://example.invalid/report-a",
    retrieved: "19 Oct 2026, 08:30 UTC (demo clock)", hash: "demo-6d4f…91ab",
    evidence: "Source metadata record", confidence: "Unassessed",
    rationale: "Awaiting source-terms confirmation and document review.", x: 39, y: 39,
  },
  {
    id: "e2", status: "provisional", title: "Illustrative access constraint report",
    type: "Humanitarian access", place: "Arabian Peninsula · illustrative",
    when: "17 Oct 2026, 08:05 UTC (fictional)",
    summary: "An invented example of how a source-reported access constraint could be presented with explicit provisional status and limited confidence.",
    source: "Example Publisher B", url: "https://example.invalid/report-b",
    retrieved: "19 Oct 2026, 08:34 UTC (demo clock)", hash: "demo-b90a…0c31",
    evidence: "Metadata link + analyst note", confidence: "Provisional example",
    rationale: "One fictional report is linked; corroboration is not represented.", x: 45, y: 44,
  },
  {
    id: "e3", status: "verified", title: "Illustrative humanitarian access update",
    type: "Humanitarian access", place: "Red Sea region · illustrative",
    when: "16 Oct 2026, 11:40 UTC (fictional)",
    summary: "A fabricated record used to preview a verified-state label and evidence summary. No actual event is being reported.",
    source: "Example Publisher C", url: "https://example.invalid/report-c",
    retrieved: "19 Oct 2026, 08:40 UTC (demo clock)", hash: "demo-4a72…fd20",
    evidence: "Two fictional references", confidence: "Verified-state demo",
    rationale: "Interface behavior only. No factual evaluation has been performed.", x: 65, y: 65,
  },
  {
    id: "e4", status: "provisional", title: "Illustrative displacement reporting",
    type: "Displacement", place: "Eastern Mediterranean · illustrative",
    when: "15 Oct 2026, 19:10 UTC (fictional)",
    summary: "A fictional humanitarian reporting entry. Any numerical estimate would require source-specific definitions, coverage, geography, period and uncertainty.",
    source: "Example Publisher D", url: "https://example.invalid/report-d",
    retrieved: "19 Oct 2026, 08:43 UTC (demo clock)", hash: "demo-8f21…2a10",
    evidence: "Metadata-only fixture", confidence: "Provisional example",
    rationale: "Showing the review panel structure; not a population estimate.", x: 34, y: 53,
  },
  {
    id: "e5", status: "verified", title: "Illustrative public-facility report",
    type: "Infrastructure damage", place: "West Asia · illustrative",
    when: "14 Oct 2026, 06:30 UTC (fictional)",
    summary: "Demonstration of source-link and version information. The marker position is illustrative and is not a coordinate for a real incident.",
    source: "Example Publisher E", url: "https://example.invalid/report-e",
    retrieved: "19 Oct 2026, 08:45 UTC (demo clock)", hash: "demo-cc19…71e2",
    evidence: "Two fictional references", confidence: "Verified-state demo",
    rationale: "Used only to test the details pane and navigation.", x: 56, y: 59,
  },
];

const TABS = [
  { id: "overview", label: "Overview", icon: "◫" },
  { id: "events", label: "Event explorer", icon: "⌕" },
  { id: "satellite", label: "Satellite observations", icon: "◎" },
  { id: "humanitarian", label: "Humanitarian indicators", icon: "＋" },
  { id: "maritime", label: "Maritime aggregates", icon: "⇄" },
  { id: "methodology", label: "Methodology & provenance", icon: "≡" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function statusLabel(status: DemoStatus) {
  if (status === "verified") return "Verified · demo";
  if (status === "provisional") return "Provisional · demo";
  return "Needs review";
}

function StatusTag({ status }: { status: DemoStatus }) {
  return <span className={"mcho-tag mcho-tag-" + status}>{statusLabel(status)}</span>;
}

function Metric({ label, value, note, icon }: { label: string; value: string; note: string; icon: string }) {
  return (
    <article className="mcho-metric">
      <div className="mcho-metric-head"><span>{label}</span><span aria-hidden="true" className="mcho-metric-icon">{icon}</span></div>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

export default function DemoExperience() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selectedId, setSelectedId] = useState("e1");
  const [toast, setToast] = useState("");

  const selected = DEMO_RECORDS.find((record) => record.id === selectedId) || DEMO_RECORDS[0];
  const filteredRecords = useMemo(() => {
    const query = search.trim().toLowerCase();
    return DEMO_RECORDS.filter((record) => {
      const matchesStatus = statusFilter === "all" || record.status === statusFilter;
      const haystack = [record.title, record.type, record.place, record.source].join(" ").toLowerCase();
      return matchesStatus && (!query || haystack.includes(query));
    });
  }, [search, statusFilter]);

  function selectRecord(id: string) {
    setSelectedId(id);
    setToast("");
  }

  async function copyProvenance() {
    const value = selected.title + "\n" + selected.url + "\n" + selected.hash + "\nSYNTHETIC DEMO — NOT A REAL SOURCE";
    try {
      await navigator.clipboard.writeText(value);
      setToast("Synthetic provenance copied. It is not a real source or incident.");
    } catch {
      setToast(value);
    }
  }

  function previewReview() {
    setToast("Preview only: review and publication actions are disabled in this standalone demo.");
  }

  function renderFilters() {
    return (
      <div className="mcho-filters">
        <label className="mcho-search">
          <span className="mcho-visually-hidden">Search synthetic records</span>
          <span aria-hidden="true">⌕</span>
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search example records…" />
        </label>
        <label>
          <span className="mcho-visually-hidden">Filter records by status</span>
          <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
            <option value="all">All statuses</option>
            <option value="review">Needs review</option>
            <option value="provisional">Provisional</option>
            <option value="verified">Verified · demo</option>
          </select>
        </label>
      </div>
    );
  }

  function renderRecordList(compact = false) {
    if (!filteredRecords.length) {
      return <div className="mcho-empty">No synthetic records match these filters. Try a different search or status.</div>;
    }
    return (
      <div className={compact ? "mcho-record-list mcho-record-list-compact" : "mcho-record-list"}>
        {filteredRecords.map((record) => (
          <button key={record.id} type="button" onClick={() => selectRecord(record.id)} className={"mcho-record " + (selectedId === record.id ? "is-selected" : "")}>
            <span className="mcho-record-heading"><strong>{record.title}</strong><StatusTag status={record.status} /></span>
            <span className="mcho-record-type">{record.type} <span aria-hidden="true">·</span> {record.place}</span>
            <span className="mcho-record-meta"><span>◷ {record.when}</span><span>▤ {record.source}</span></span>
          </button>
        ))}
      </div>
    );
  }

  function renderDetail() {
    return (
      <section className="mcho-panel mcho-detail-panel" aria-label="Selected synthetic record">
        <div className="mcho-panel-head">
          <div><h2>Selected record</h2><p className="mcho-sub">{selected.id.toUpperCase()} · synthetic fixture</p></div>
          <StatusTag status={selected.status} />
        </div>
        <div className="mcho-detail">
          <div className="mcho-kicker">{selected.type}</div>
          <h3>{selected.title}</h3>
          <p className="mcho-detail-summary">{selected.summary}</p>
          <div className="mcho-detail-grid">
            <div><span>Illustrative location</span><strong>{selected.place}</strong></div>
            <div><span>Reported time</span><strong>{selected.when}</strong></div>
            <div><span>Source</span><strong>{selected.source}</strong></div>
            <div><span>Assessment</span><strong>{selected.confidence}</strong></div>
          </div>
          <div className="mcho-separator" />
          <h4>Provenance & evidence</h4>
          <div className="mcho-evidence">
            <div className="mcho-record-heading"><strong>{selected.evidence}</strong><span className="mcho-tag mcho-tag-review">Fixture</span></div>
            <p>Canonical link: <code>{selected.url}</code></p>
            <p>Retrieved: {selected.retrieved}</p>
            <p>Content hash: {selected.hash}</p>
            <small>✓ Metadata-only example · original content not stored</small>
          </div>
          <div className="mcho-review-note"><strong>Review note</strong><span>{selected.rationale}</span></div>
          <div className="mcho-guardrail">
            <strong>Interpretation limit</strong>
            <p>This record is invented for interface testing. Its status label has no factual meaning.</p>
          </div>
          <div className="mcho-actions">
            <button type="button" className="mcho-button" onClick={previewReview}>Preview review action</button>
            <button type="button" className="mcho-button mcho-button-secondary" onClick={copyProvenance}>Copy demo provenance</button>
          </div>
        </div>
      </section>
    );
  }

  function renderMap() {
    return (
      <section className="mcho-panel">
        <div className="mcho-panel-head">
          <div><h2>Regional overview</h2><p className="mcho-sub">Illustrative marker plot · not geographic evidence</p></div>
          <div className="mcho-panel-tools">
            <button type="button" className="mcho-mini-button" onClick={() => selectRecord("e1")}>Reset selection</button>
            <button type="button" className="mcho-mini-button" onClick={() => setToast("Focus is illustrative only; the marker plot is not geographically accurate.")}>Focus selected</button>
          </div>
        </div>
        <div className="mcho-map-area">
          <div className="mcho-map-caption">MENA · Demonstration layer</div>
          <svg viewBox="0 0 760 430" role="img" aria-label="Illustrative regional marker plot; not a geographic map">
            <defs>
              <linearGradient id="mcho-sea" x1="0" x2="1"><stop offset="0" stopColor="#102333" /><stop offset="1" stopColor="#132c3e" /></linearGradient>
              <pattern id="mcho-grid" width="38" height="38" patternUnits="userSpaceOnUse"><path d="M 38 0 L 0 0 0 38" fill="none" stroke="#85abc7" strokeOpacity=".09" strokeWidth="1" /></pattern>
            </defs>
            <rect width="760" height="430" fill="url(#mcho-sea)" />
            <rect width="760" height="430" fill="url(#mcho-grid)" />
            <path d="M58 80 L104 53 L172 70 L200 109 L245 113 L268 157 L244 191 L202 184 L174 216 L130 205 L118 250 L77 238 L50 194 Z" fill="#3c5963" fillOpacity=".65" stroke="#7695a0" strokeOpacity=".35" />
            <path d="M257 95 L305 65 L355 82 L390 109 L427 105 L469 136 L452 173 L423 191 L400 230 L369 244 L352 287 L316 292 L287 251 L291 216 L260 191 L244 153 Z" fill="#3c5963" fillOpacity=".68" stroke="#7695a0" strokeOpacity=".35" />
            <path d="M430 193 L483 173 L533 181 L566 222 L596 239 L606 290 L580 320 L541 300 L507 272 L475 252 L447 225 Z" fill="#3c5963" fillOpacity=".6" stroke="#7695a0" strokeOpacity=".35" />
            <path d="M508 287 L552 307 L586 340 L574 375 L548 362 L529 332 Z" fill="#3c5963" fillOpacity=".55" stroke="#7695a0" strokeOpacity=".35" />
            <path d="M102 282 L143 263 L181 283 L194 313 L168 329 L130 323 Z" fill="#3c5963" fillOpacity=".55" stroke="#7695a0" strokeOpacity=".35" />
            <text x="86" y="153" className="mcho-map-watermark">NORTH AFRICA</text>
            <text x="292" y="160" className="mcho-map-watermark">LEVANT</text>
            <text x="466" y="244" className="mcho-map-watermark">ARABIAN PENINSULA</text>
            <text x="615" y="90" className="mcho-map-watermark">WEST ASIA</text>
            {DEMO_RECORDS.map((record) => (
              <g key={record.id} className={"mcho-map-point " + (record.status === "provisional" ? "is-provisional " : "") + (selectedId === record.id ? "is-selected" : "")}
                role="button" tabIndex={0} aria-label={"Select " + record.title}
                onClick={() => selectRecord(record.id)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectRecord(record.id); } }}>
                <circle className="mcho-point-outer" cx={record.x * 7.6} cy={record.y * 4.3} r={selectedId === record.id ? 17 : 13} />
                <circle className="mcho-point-inner" cx={record.x * 7.6} cy={record.y * 4.3} r="4.5" />
              </g>
            ))}
            <text x="20" y="414" className="mcho-map-footer">ILLUSTRATIVE PANEL · BOUNDARIES NOT FOR REFERENCE</text>
          </svg>
          <div className="mcho-map-legend"><span><i className="mcho-legend-dot mcho-dot-teal" />Verified status (demo)</span><span><i className="mcho-legend-dot mcho-dot-amber" />Provisional (demo)</span><span>○ Review candidate</span></div>
        </div>
        <div className="mcho-map-foot"><span>Illustrative markers only · no live geospatial data</span><span>Source provenance on selection</span></div>
      </section>
    );
  }

  function renderOverview() {
    return (
      <>
        <div className="mcho-metrics">
          <Metric label="Review candidates" value="01" note="One fictional record awaiting review" icon="◉" />
          <Metric label="Evidence-linked records" value="05" note="Synthetic provenance examples" icon="⌁" />
          <Metric label="Satellite candidates" value="02" note="Examples, not damage assessments" icon="◎" />
          <Metric label="Data connectors" value="00" note="Production feeds are disabled" icon="⇄" />
        </div>
        <div className="mcho-content-grid">
          <div className="mcho-main-column">{renderMap()}</div>
          <aside className="mcho-side-column">
            <section className="mcho-panel">
              <div className="mcho-panel-head"><div><h2>Evidence & review queue</h2><p className="mcho-sub">Select a record to inspect traceability</p></div><span className="mcho-chip">Demo fixtures</span></div>
              {renderFilters()}
              <div className="mcho-feed">{renderRecordList(true)}</div>
            </section>
            {renderDetail()}
          </aside>
        </div>
        <div className="mcho-bottom-grid">
          <section className="mcho-panel">
            <div className="mcho-panel-head"><div><h2>Source freshness & connector status</h2><p className="mcho-sub">Prototype controls, not live monitoring</p></div><span className="mcho-chip">Disabled by default</span></div>
            <div className="mcho-compact-list">
              <div><strong>ReliefWeb metadata adapter</strong><span className="mcho-warn">Not configured</span></div>
              <div><strong>HDX humanitarian indicators</strong><span className="mcho-warn">Not enabled</span></div>
              <div><strong>Satellite scene catalog</strong><span className="mcho-warn">Not enabled</span></div>
              <div><strong>Maritime aggregate feed</strong><span className="mcho-warn">Not enabled</span></div>
            </div>
          </section>
          <section className="mcho-panel">
            <div className="mcho-panel-head"><div><h2>Publication guardrails</h2><p className="mcho-sub">Intended server-enforced workflow</p></div></div>
            <div className="mcho-compact-list">
              <div><strong>Source terms reviewed</strong><span className="mcho-good">Required</span></div>
              <div><strong>Evidence document approved</strong><span className="mcho-good">Required</span></div>
              <div><strong>Independent editor, reviewer and publisher</strong><span className="mcho-good">Required</span></div>
              <div><strong>Correction creates a new revision</strong><span className="mcho-good">Required</span></div>
            </div>
          </section>
        </div>
      </>
    );
  }

  function renderEvents() {
    return (
      <div className="mcho-events-grid">
        <section className="mcho-panel">
          <div className="mcho-panel-head"><div><h2>Event explorer</h2><p className="mcho-sub">Search and filter synthetic example records</p></div></div>
          {renderFilters()}
          <div className="mcho-feed">{renderRecordList()}</div>
        </section>
        {renderDetail()}
      </div>
    );
  }

  function renderSatellite() {
    return <section className="mcho-panel">
      <div className="mcho-panel-head"><div><h2>Satellite observations</h2><p className="mcho-sub">Scene discovery and candidate review · not automatic damage conclusions</p></div><span className="mcho-chip">Prototype module</span></div>
      <div className="mcho-module-grid">
        <article className="mcho-module-card"><div className="mcho-kicker">Candidate S-001</div><h3>Before / after scene pair</h3><p>Example metadata: two fictional observation dates, cloud cover, resolution and processing lineage. No real scene was fetched.</p><span className="mcho-tag mcho-tag-review">Needs analyst review</span></article>
        <article className="mcho-module-card"><div className="mcho-kicker">Candidate S-002</div><h3>Surface-change signal</h3><p>Illustrative change scores can be influenced by seasonality, shadows, clouds, or image-registration error.</p><span className="mcho-tag mcho-tag-provisional">Unvalidated</span></article>
        <article className="mcho-module-card"><div className="mcho-kicker">Quality checklist</div><h3>Reproducibility</h3><p>Retain source scene IDs, timestamps, processing version, area of interest, cloud mask, interval and analyst decision.</p><span className="mcho-tag mcho-tag-review">Review required</span></article>
      </div>
    </section>;
  }

  function renderHumanitarian() {
    return <section className="mcho-panel">
      <div className="mcho-panel-head"><div><h2>Humanitarian indicators</h2><p className="mcho-sub">Coverage, unit, period and source must accompany each value</p></div><span className="mcho-chip">Sample schema</span></div>
      <div className="mcho-compact-list mcho-humanitarian-list">
        <div><strong>Displaced population (fictional)</strong><span>Unit: people · Period: demo</span></div>
        <div><strong>Health facilities reported non-functional (fictional)</strong><span>Unit: facilities · Period: demo</span></div>
        <div><strong>Food access assessment (fictional)</strong><span>Unit: classification · Period: demo</span></div>
        <div><strong>Coverage / uncertainty</strong><span className="mcho-warn">Must be shown with every value</span></div>
      </div>
    </section>;
  }

  function renderMaritime() {
    return <section className="mcho-panel">
      <div className="mcho-panel-head"><div><h2>Maritime aggregates</h2><p className="mcho-sub">Broad, delayed, aggregate indicators only</p></div><span className="mcho-chip">No AIS connection</span></div>
      <div className="mcho-module-grid">
        <article className="mcho-module-card"><div className="mcho-kicker">Regional transit index</div><h3>100.0</h3><p>Fictional normalized baseline used to illustrate aggregate display; not a real corridor assessment.</p></article>
        <article className="mcho-module-card"><div className="mcho-kicker">Coverage status</div><h3>Not supplied</h3><p>No inference is made from missing input or coverage gaps.</p></article>
        <article className="mcho-module-card"><div className="mcho-kicker">Safety scope</div><h3>Aggregate only</h3><p>No vessel-level live tracks, sensitive routes, tactical predictions or targeting outputs.</p></article>
      </div>
    </section>;
  }

  function renderMethodology() {
    const cards = [
      ["1 · Report", "Source says", "Retain publisher, publication date, canonical URL and retrieval time. API access alone does not grant redistribution rights."],
      ["2 · Review", "Human assessment", "Analysts record rationale and distinguish source claims from verified events. Document review is independent from event publication."],
      ["3 · Publish", "Independent approval", "Publication requires a positive review after the latest revision, a distinct publisher and eligible evidence."],
      ["4 · Correct", "Visible history", "Corrections create immutable revisions, reset verification and reopen review instead of silently changing an earlier record."],
      ["5 · Uncertainty", "Confidence is not truth", "Keep source count, reliability, time uncertainty, location uncertainty and coverage limitations separate."],
      ["6 · Limits", "Missing data ≠ no event", "Absent reporting, imagery or maritime coverage is never proof that nothing happened."]
    ];
    return <div className="mcho-method-grid">{cards.map((card) => <article key={card[0]} className="mcho-module-card"><div className="mcho-kicker">{card[0]}</div><h3>{card[1]}</h3><p>{card[2]}</p></article>)}</div>;
  }

  function renderActiveModule() {
    if (activeTab === "overview") return renderOverview();
    if (activeTab === "events") return renderEvents();
    if (activeTab === "satellite") return renderSatellite();
    if (activeTab === "humanitarian") return renderHumanitarian();
    if (activeTab === "maritime") return renderMaritime();
    return renderMethodology();
  }

  return (
    <main className="mcho-demo-shell">
      <header className="mcho-topbar">
        <a className="mcho-brand" href="/" aria-label="Back to the MCHO application home">
          <span className="mcho-brand-mark">M</span>
          <span><span className="mcho-eyebrow">Evidence-first regional monitoring</span><h1 className="mcho-title">MENA Conflict & Humanitarian Observatory</h1></span>
        </a>
        <div className="mcho-top-actions"><span className="mcho-mode-chip"><i /> Design preview · sample data</span><span className="mcho-version-chip">UI preview · v0.2</span><a href="/" className="mcho-back-link">Go to the live satellite map ↗</a></div>
      </header>

      <section className="mcho-demo-warning" role="note">
        <span aria-hidden="true" className="mcho-warning-icon">ⓘ</span>
        <div><strong>Prototype data — not live conflict information</strong><p>All events, reports, indicators, locations and metrics shown here are invented interface fixtures. Do not cite them, interpret them as current incidents, or use them for operational decisions. Map markers are illustrative.</p></div>
      </section>

      <nav className="mcho-tabs" aria-label="Observatory sections" role="tablist">
        {TABS.map((tab) => <button key={tab.id} type="button" role="tab" aria-selected={activeTab === tab.id} className={activeTab === tab.id ? "is-active" : ""} onClick={() => setActiveTab(tab.id)}><span aria-hidden="true">{tab.icon}</span>{tab.label}</button>)}
      </nav>

      {renderActiveModule()}

      <footer className="mcho-demo-footer"><span>MCHO · Interactive prototype · Synthetic fixtures only</span><span>No backend · No external requests · No live feeds · Not for operational use</span></footer>
      {toast ? <div className="mcho-toast" role="status"><span>{toast}</span><button type="button" aria-label="Dismiss message" onClick={() => setToast("")}>×</button></div> : null}
    </main>
  );
}
