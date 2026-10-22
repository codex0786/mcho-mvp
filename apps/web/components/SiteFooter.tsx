export default function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="footer-brand">
          <strong>MCHO</strong>
          <p>MENA Conflict &amp; Humanitarian Observatory. A demonstration of evidence-first monitoring from open data.</p>
          <p className="footer-warning">Not for tactical or targeting decisions.</p>
        </div>
        <div>
          <h3>Sources</h3>
          <ul>
            <li>Satellite heat: NASA FIRMS (VIIRS)</li>
            <li>Verified violence: UCDP Candidate Events, CC BY 4.0</li>
            <li>Damage: UNOSAT via HDX, CC BY-SA</li>
            <li>Shipping: IMF PortWatch</li>
            <li>Imagery: Copernicus Sentinel-2; EOX Sentinel-2 cloudless</li>
          </ul>
        </div>
        <div>
          <h3>Map</h3>
          <ul>
            <li>Borders: Natural Earth</li>
            <li>Basemap: OpenFreeMap, © OpenStreetMap contributors</li>
            <li>Satellite view: Sentinel-2 cloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data), CC BY-NC-SA 4.0</li>
          </ul>
        </div>
        <div>
          <h3>Explore</h3>
          <ul>
            <li><a href="/#map">Live map</a></li>
            <li><a href="/about">About the data</a></li>
            <li><a href="/demo">Design preview (sample data)</a></li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
